"""
Phase 2 - Cloud Dashboard Development
Azure Function (Python v2 programming model)

This function is the cloud evolution of Phase 1's lambda_function.py.
Instead of reading the diets dataset from Azurite (local emulator), it
reads it from a real Azure Blob Storage container, cleans it, computes
the same nutritional insights, and returns them as JSON so the web
dashboard can render charts from them.

Two trigger styles are used on purpose, to contrast request/response vs
event-driven communication:
  - HTTP triggers (get_nutritional_insights, get_diet_types, get_correlations,
    get_recipes, get_clusters, health_check): synchronous - a client sends a
    request and waits for a response. This is the "message" side of the
    messages-vs-events distinction: a direct command to one handler.
  - Blob trigger (on_dataset_uploaded): event-driven - no client calls it
    directly. Azure Storage broadcasts a "blob created/updated" event and
    this function reacts automatically, with no one waiting on a response.
    This is the "event" side: a fact ("a file changed") that any interested
    subscriber can react to.

Observability: every request logs structured fields (via logging's `extra`)
so that once Application Insights is linked to this Function App, these
show up as custom dimensions on traces - letting you filter/query requests
by diet_filter, row_count, k, etc. instead of just reading raw text logs.

Environment variables expected (set in Azure Function App > Configuration,
or in local.settings.json for local testing):
    AZURE_STORAGE_CONNECTION_STRING  - connection string for the storage account
    BLOB_CONTAINER_NAME              - defaults to "datasets"
    BLOB_NAME                        - defaults to "All_Diets.csv"
"""

import io
import json
import logging
import math
import os
import time

import azure.functions as func
import pandas as pd
from azure.storage.blob import BlobServiceClient
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

NEEDED_COLUMNS = ["Diet_type", "Recipe_name", "Cuisine_type", "Protein(g)", "Carbs(g)", "Fat(g)"]
NUMERIC_COLUMNS = ["Protein(g)", "Carbs(g)", "Fat(g)"]


def _load_dataset_from_blob() -> pd.DataFrame:
    """Downloads the dataset CSV from Azure Blob Storage and returns a DataFrame."""
    connect_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
    container_name = os.environ.get("BLOB_CONTAINER_NAME", "datasets")
    blob_name = os.environ.get("BLOB_NAME", "All_Diets.csv")

    blob_service_client = BlobServiceClient.from_connection_string(connect_str)
    container_client = blob_service_client.get_container_client(container_name)
    blob_client = container_client.get_blob_client(blob_name)

    logging.info(f"Downloading {blob_name} from container '{container_name}'...")
    stream = blob_client.download_blob().readall()
    df = pd.read_csv(io.BytesIO(stream), usecols=NEEDED_COLUMNS)
    logging.info(f"Loaded {len(df)} rows from blob storage.")
    return df


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    for col in NUMERIC_COLUMNS:
        df[col] = df[col].fillna(df[col].mean())
    return df


def _apply_diet_filter(df: pd.DataFrame, diet_filter: str | None = None) -> pd.DataFrame:
    """Shared helper: filters the dataset to a single diet type, or returns it unchanged."""
    if diet_filter:
        df = df[df["Diet_type"].str.lower() == diet_filter.lower()]
        if df.empty:
            raise ValueError(f"No rows found for diet_type='{diet_filter}'")
    return df


def _analyze(df: pd.DataFrame, diet_filter: str | None = None) -> dict:
    df = _apply_diet_filter(df, diet_filter)

    # 1. Average macronutrients per diet type (bar chart source)
    avg_macros = df.groupby("Diet_type")[NUMERIC_COLUMNS].mean().round(2)

    # 2. Top 5 protein-rich recipes per diet type (scatter chart source)
    top_protein = (
        df.sort_values("Protein(g)", ascending=False)
        .groupby("Diet_type")
        .head(5)[["Diet_type", "Recipe_name", "Cuisine_type", "Protein(g)"]]
    )

    # 3. Diet type with the highest average protein
    highest_protein_diet = avg_macros["Protein(g)"].idxmax()

    # 4. Most common cuisine per diet type (pie/bar chart source)
    common_cuisine = df.groupby("Diet_type")["Cuisine_type"].agg(lambda x: x.mode()[0])

    return {
        "row_count": int(len(df)),
        "avg_macros": avg_macros.reset_index().to_dict(orient="records"),
        "top_protein_recipes": top_protein.to_dict(orient="records"),
        "highest_protein_diet": highest_protein_diet,
        "common_cuisine_per_diet": common_cuisine.reset_index().to_dict(orient="records"),
    }


def _correlations(df: pd.DataFrame, diet_filter: str | None = None) -> dict:
    """
    Pearson correlation matrix between the numeric macronutrient columns.
    Powers the dashboard's nutrient-correlation Heatmap card.
    """
    df = _apply_diet_filter(df, diet_filter)

    corr = df[NUMERIC_COLUMNS].corr().round(3)
    matrix = [
        {"x": x_col, "y": y_col, "value": float(corr.loc[y_col, x_col])}
        for y_col in NUMERIC_COLUMNS
        for x_col in NUMERIC_COLUMNS
    ]

    return {
        "row_count": int(len(df)),
        "labels": NUMERIC_COLUMNS,
        "matrix": matrix,
    }


def _paginate_recipes(df: pd.DataFrame, diet_filter: str | None, page: int, page_size: int) -> dict:
    """
    Returns one page of individual recipe rows. Powers the "Get Recipes"
    button and the Pagination controls on the dashboard.
    """
    df = _apply_diet_filter(df, diet_filter)

    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    total_rows = int(len(df))
    total_pages = max(math.ceil(total_rows / page_size), 1)
    page = min(page, total_pages)

    start = (page - 1) * page_size
    end = start + page_size
    page_df = df.iloc[start:end][["Diet_type", "Recipe_name", "Cuisine_type"] + NUMERIC_COLUMNS]

    return {
        "page": page,
        "page_size": page_size,
        "total_rows": total_rows,
        "total_pages": total_pages,
        "recipes": page_df.to_dict(orient="records"),
    }


def _cluster(df: pd.DataFrame, diet_filter: str | None, k: int, sample_size: int = 300) -> dict:
    """
    K-Means clustering of recipes by macronutrient profile (Protein/Carbs/Fat).
    Powers the "Get Clusters" button - groups recipes with similar nutrition
    into k clusters, independent of their labeled Diet_type.
    """
    df = _apply_diet_filter(df, diet_filter)

    k = min(max(k, 2), 8)
    k = min(k, len(df))  # can't have more clusters than rows

    features = df[NUMERIC_COLUMNS].to_numpy()
    scaled = StandardScaler().fit_transform(features)

    model = KMeans(n_clusters=k, n_init=10, random_state=42)
    labels = model.fit_predict(scaled)

    clustered = df[["Recipe_name", "Diet_type", "Cuisine_type"] + NUMERIC_COLUMNS].copy()
    clustered["cluster"] = labels

    centers = (
        clustered.groupby("cluster")[NUMERIC_COLUMNS]
        .mean()
        .round(2)
        .reset_index()
        .rename(columns={c: f"avg_{c}" for c in NUMERIC_COLUMNS})
    )
    counts = clustered.groupby("cluster").size().rename("count")
    centers = centers.merge(counts, on="cluster")

    sample = clustered.sample(n=min(sample_size, len(clustered)), random_state=42)

    return {
        "k": k,
        "row_count": int(len(df)),
        "cluster_centers": centers.to_dict(orient="records"),
        "sample_points": sample.to_dict(orient="records"),
    }


@app.route(route="insights", methods=["GET"])
def get_nutritional_insights(req: func.HttpRequest) -> func.HttpResponse:
    """
    GET /api/insights
    GET /api/insights?diet_type=keto

    Returns nutritional insight data (averages, top recipes, most common
    cuisines) computed live from the dataset in Azure Blob Storage, plus
    function execution time metadata for the dashboard to display.
    """
    start = time.perf_counter()
    diet_filter = req.params.get("diet_type")

    try:
        df = _load_dataset_from_blob()
        df = _clean(df)
        result = _analyze(df, diet_filter)
    except ValueError as ve:
        return func.HttpResponse(
            json.dumps({"error": str(ve)}),
            status_code=404,
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )
    except Exception as e:
        logging.exception("Failed to process nutritional insights")
        return func.HttpResponse(
            json.dumps({"error": f"Internal error: {e}"}),
            status_code=500,
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    result["execution_time_ms"] = elapsed_ms
    result["diet_filter_applied"] = diet_filter or "all"

    # Structured log line: with Application Insights linked, diet_filter/row_count/
    # elapsed_ms become queryable custom dimensions on this request's trace,
    # instead of being buried in free-text.
    logging.info(
        "insights served",
        extra={
            "diet_filter": diet_filter or "all",
            "row_count": result["row_count"],
            "elapsed_ms": elapsed_ms,
        },
    )

    return func.HttpResponse(
        json.dumps(result, indent=2),
        status_code=200,
        mimetype="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """
    GET /api/health

    Lightweight liveness/readiness check that does NOT touch Blob Storage -
    used to verify the Function App itself is up, independent of whether the
    dataset is reachable. Standard operational-excellence practice: a
    dashboard, uptime monitor, or load balancer can poll this cheaply instead
    of hitting a heavy data endpoint just to check "is it alive".
    """
    return _json_response({"status": "ok", "service": "diet-analysis-func"})


@app.route(route="diet_types", methods=["GET"])
def get_diet_types(req: func.HttpRequest) -> func.HttpResponse:
    """GET /api/diet_types - returns the distinct diet types, used to populate the dashboard filter dropdown."""
    try:
        df = _load_dataset_from_blob()
        diet_types = sorted(df["Diet_type"].dropna().unique().tolist())
    except Exception as e:
        logging.exception("Failed to fetch diet types")
        return func.HttpResponse(
            json.dumps({"error": f"Internal error: {e}"}),
            status_code=500,
            mimetype="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )

    return func.HttpResponse(
        json.dumps({"diet_types": diet_types}),
        status_code=200,
        mimetype="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


def _json_response(payload: dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, indent=2, default=str),
        status_code=status_code,
        mimetype="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


@app.route(route="correlations", methods=["GET"])
def get_correlations(req: func.HttpRequest) -> func.HttpResponse:
    """
    GET /api/correlations
    GET /api/correlations?diet_type=keto

    Returns a Protein/Carbs/Fat correlation matrix, used to render the
    dashboard's nutrient-correlation Heatmap.
    """
    start = time.perf_counter()
    diet_filter = req.params.get("diet_type")

    try:
        df = _clean(_load_dataset_from_blob())
        result = _correlations(df, diet_filter)
    except ValueError as ve:
        return _json_response({"error": str(ve)}, 404)
    except Exception as e:
        logging.exception("Failed to compute correlations")
        return _json_response({"error": f"Internal error: {e}"}, 500)

    result["execution_time_ms"] = round((time.perf_counter() - start) * 1000, 2)
    result["diet_filter_applied"] = diet_filter or "all"

    logging.info(
        "correlations served",
        extra={
            "diet_filter": diet_filter or "all",
            "row_count": result["row_count"],
            "elapsed_ms": result["execution_time_ms"],
        },
    )
    return _json_response(result)


@app.route(route="recipes", methods=["GET"])
def get_recipes(req: func.HttpRequest) -> func.HttpResponse:
    """
    GET /api/recipes
    GET /api/recipes?diet_type=keto&page=2&page_size=10

    Returns one page of individual recipe rows for the "Get Recipes"
    button + pagination controls on the dashboard.
    """
    start = time.perf_counter()
    diet_filter = req.params.get("diet_type")
    try:
        page = int(req.params.get("page", 1))
        page_size = int(req.params.get("page_size", 10))
    except ValueError:
        return _json_response({"error": "page and page_size must be integers"}, 400)

    try:
        df = _clean(_load_dataset_from_blob())
        result = _paginate_recipes(df, diet_filter, page, page_size)
    except ValueError as ve:
        return _json_response({"error": str(ve)}, 404)
    except Exception as e:
        logging.exception("Failed to fetch recipes")
        return _json_response({"error": f"Internal error: {e}"}, 500)

    result["execution_time_ms"] = round((time.perf_counter() - start) * 1000, 2)
    result["diet_filter_applied"] = diet_filter or "all"

    logging.info(
        "recipes served",
        extra={
            "diet_filter": diet_filter or "all",
            "page": result["page"],
            "total_rows": result["total_rows"],
            "elapsed_ms": result["execution_time_ms"],
        },
    )
    return _json_response(result)


@app.route(route="clusters", methods=["GET"])
def get_clusters(req: func.HttpRequest) -> func.HttpResponse:
    """
    GET /api/clusters
    GET /api/clusters?diet_type=keto&k=4

    Runs K-Means on the macronutrient profile (Protein/Carbs/Fat) of each
    recipe and returns cluster centers + a sample of labeled points, for
    the "Get Clusters" button on the dashboard.
    """
    start = time.perf_counter()
    diet_filter = req.params.get("diet_type")
    try:
        k = int(req.params.get("k", 4))
    except ValueError:
        return _json_response({"error": "k must be an integer"}, 400)

    try:
        df = _clean(_load_dataset_from_blob())
        result = _cluster(df, diet_filter, k)
    except ValueError as ve:
        return _json_response({"error": str(ve)}, 404)
    except Exception as e:
        logging.exception("Failed to compute clusters")
        return _json_response({"error": f"Internal error: {e}"}, 500)

    result["execution_time_ms"] = round((time.perf_counter() - start) * 1000, 2)
    result["diet_filter_applied"] = diet_filter or "all"

    logging.info(
        "clusters served",
        extra={
            "diet_filter": diet_filter or "all",
            "k": result["k"],
            "row_count": result["row_count"],
            "elapsed_ms": result["execution_time_ms"],
        },
    )
    return _json_response(result)


# ============================================================================
# EVENT-DRIVEN: Blob Trigger (contrast with the HTTP/request-response routes above)
# ============================================================================
#
# Every function above is a "message" handler: a client sends an HTTP request
# and is blocked waiting for a direct response. This function is different -
# it is an "event" subscriber: nobody calls it directly. Azure Blob Storage
# broadcasts a fact ("this blob was created or updated") whenever a file
# lands in the "datasets" container, and the Functions runtime wakes this
# handler up automatically to react. There is no caller waiting on a
# response, and multiple independent subscribers could react to the same
# blob event without knowing about each other (fan-out) - the defining traits
# of event-driven communication versus point-to-point request/response.
#
# Practical use here: whenever someone uploads a refreshed All_Diets.csv
# (e.g. via upload_dataset_to_cloud.py), this validates the new file's shape
# automatically - no one has to remember to call a "validate" endpoint.
@app.blob_trigger(arg_name="myblob", path="datasets/{name}", connection="AZURE_STORAGE_CONNECTION_STRING")
def on_dataset_uploaded(myblob: func.InputStream) -> None:
    size_kb = round(myblob.length / 1024, 1) if myblob.length else 0
    logging.info(
        "dataset blob event received",
        extra={"blob_name": myblob.name, "size_kb": size_kb},
    )

    if not myblob.name.lower().endswith(".csv"):
        logging.info(f"[event] Skipping non-CSV blob: {myblob.name}")
        return

    try:
        df = pd.read_csv(myblob, usecols=NEEDED_COLUMNS)
        missing_values = int(df[NUMERIC_COLUMNS].isna().sum().sum())
        logging.info(
            "dataset validated",
            extra={
                "blob_name": myblob.name,
                "row_count": len(df),
                "missing_values": missing_values,
            },
        )
    except Exception as e:
        # Validation failures are logged (and would show up as a failed
        # trace / exception in Application Insights) rather than raised,
        # since there's no HTTP caller here to return an error response to.
        logging.error(f"[event] Dataset validation failed for {myblob.name}: {e}")
