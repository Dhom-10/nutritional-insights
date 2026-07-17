"""
Phase 2 - Cloud Dashboard Development
Azure Function (Python v2 programming model, HTTP trigger)

This function is the cloud evolution of Phase 1's lambda_function.py.
Instead of reading the diets dataset from Azurite (local emulator), it
reads it from a real Azure Blob Storage container, cleans it, computes
the same nutritional insights, and returns them as JSON so the web
dashboard can render charts from them.

Environment variables expected (set in Azure Function App > Configuration,
or in local.settings.json for local testing):
    AZURE_STORAGE_CONNECTION_STRING  - connection string for the storage account
    BLOB_CONTAINER_NAME              - defaults to "datasets"
    BLOB_NAME                        - defaults to "All_Diets.csv"
"""

import io
import json
import logging
import os
import time

import azure.functions as func
import pandas as pd
from azure.storage.blob import BlobServiceClient

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


def _analyze(df: pd.DataFrame, diet_filter: str | None = None) -> dict:
    if diet_filter:
        df = df[df["Diet_type"].str.lower() == diet_filter.lower()]
        if df.empty:
            raise ValueError(f"No rows found for diet_type='{diet_filter}'")

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

    return func.HttpResponse(
        json.dumps(result, indent=2),
        status_code=200,
        mimetype="application/json",
        headers={"Access-Control-Allow-Origin": "*"},
    )


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
