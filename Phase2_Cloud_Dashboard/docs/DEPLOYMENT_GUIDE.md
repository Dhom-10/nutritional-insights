# Phase 2 Deployment Guide — Nutritional Insights Cloud Dashboard

This guide walks through taking Phase 1 (local Azure Function + Azurite)
to Phase 2 (real Azure cloud + web dashboard), matching the "Cloud Setup
Instructions" section of the assignment.

Repo: `github.com/Dhom-10/nutritional-insights`

## 0. Prerequisites

- Azure account with an active subscription
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) installed (`az --version`)
- [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local) (`func --version`)
- Python 3.9+ (matches Phase 1's Dockerfile base image)

```bash
az login
```

## 1. Create Resource Group + Storage Account

```bash
az group create --name diet-analysis-rg --location eastus

az storage account create \
  --name dietanalysisstorage \
  --resource-group diet-analysis-rg \
  --location eastus \
  --sku Standard_LRS
```

Get the connection string (you'll need it for both the function app config
and the local upload script):

```bash
az storage account show-connection-string \
  --name dietanalysisstorage \
  --resource-group diet-analysis-rg \
  --output tsv
```

## 2. Upload the dataset to real Azure Blob Storage

This replaces Phase 1's `upload_to_azurite.py`, which pointed at the local
emulator (`UseDevelopmentStorage=true`).

```bash
cd azure-function
export AZURE_STORAGE_CONNECTION_STRING="<paste connection string from step 1>"
pip install azure-storage-blob
python upload_dataset_to_cloud.py path/to/All_Diets.csv
```

This creates a `datasets` container and uploads `All_Diets.csv` into it.

## 3. Create the Function App

```bash
# Storage account for the Function App's own runtime state (can reuse the one above,
# or create a second dedicated one — either works for a course project)
az functionapp create \
  --resource-group diet-analysis-rg \
  --consumption-plan-location eastus \
  --runtime python \
  --runtime-version 3.9 \
  --functions-version 4 \
  --name diet-analysis-func \
  --storage-account dietanalysisstorage \
  --os-type Linux
```

Function app names are globally unique — if `diet-analysis-func` is taken,
pick another name and use it consistently below.

## 4. Configure app settings (connection string + blob names)

```bash
az functionapp config appsettings set \
  --name diet-analysis-func \
  --resource-group diet-analysis-rg \
  --settings \
    AZURE_STORAGE_CONNECTION_STRING="<paste connection string from step 1>" \
    BLOB_CONTAINER_NAME="datasets" \
    BLOB_NAME="All_Diets.csv"
```

## 5. Test locally first (optional but recommended)

```bash
cd azure-function
cp local.settings.json.example local.settings.json
# edit local.settings.json and paste your real connection string
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
func start
```

Visit `http://localhost:7071/api/insights` and `http://localhost:7071/api/diet_types`
in a browser to confirm both endpoints return JSON.

## 6. Deploy the Function

```bash
cd azure-function
func azure functionapp publish diet-analysis-func
```

> **Note:** `requirements.txt` now includes `scikit-learn` (for the
> `/api/clusters` endpoint). If you're redeploying an existing Function
> App, use `--build remote` so the new dependency actually gets installed
> in the cloud (see Troubleshooting below) — a cached local `.python_packages`
> folder won't pick it up otherwise.

Test the deployed endpoints:

```bash
curl "https://diet-analysis-func.azurewebsites.net/api/health"
curl "https://diet-analysis-func.azurewebsites.net/api/insights"
curl "https://diet-analysis-func.azurewebsites.net/api/insights?diet_type=keto"
curl "https://diet-analysis-func.azurewebsites.net/api/diet_types"
curl "https://diet-analysis-func.azurewebsites.net/api/correlations"
curl "https://diet-analysis-func.azurewebsites.net/api/recipes?page=1&page_size=10"
curl "https://diet-analysis-func.azurewebsites.net/api/clusters?k=4"
```

> **Event-driven function:** `on_dataset_uploaded` is a Blob Trigger, not an
> HTTP route, so it has no URL to curl. It deploys automatically with the
> rest of `function_app.py` in this same `func azure functionapp publish`
> step. To see it fire, upload a CSV to the `datasets` container (e.g.
> re-run `upload_dataset_to_cloud.py`, or drag a file into the container in
> the Portal) and check the Function App's **Monitor** tab a few seconds
> later — you'll see an invocation of `on_dataset_uploaded` with no HTTP
> request behind it, which is the point: it's a reaction to an event, not a
> reply to a caller.

## 7. Point the dashboard at the live function

Edit `dashboard/index.html` and update the `API_BASE_URL` constant near the
top of the `<script>` block:

```js
const API_BASE_URL = "https://diet-analysis-func.azurewebsites.net/api";
```

## 8. Deploy the dashboard (Azure Static Web App)

```bash
az staticwebapp create \
  --name diet-analysis-dashboard \
  --resource-group diet-analysis-rg \
  --location eastus2 \
  --source https://github.com/Dhom-10/nutritional-insights \
  --branch main \
  --app-location "dashboard" \
  --login-with-github
```

This walks through GitHub auth in the browser and sets up a CI/CD workflow
(similar in spirit to Phase 1's `.github/workflows/deploy.yml`) that
auto-deploys the `dashboard/` folder to Azure on every push to `main`.

Alternatively, for a simpler one-off deploy without GitHub Actions:

```bash
npm install -g @azure/static-web-apps-cli
swa deploy dashboard --deployment-token <token-from-azure-portal>
```

## 9. Observability — link Application Insights

The Function App logs structured lines (`diet_filter`, `row_count`,
`elapsed_ms`, etc.) on every request, and `host.json` already has
`applicationInsights` sampling configured — but that only becomes useful
once an actual Application Insights resource is linked.

```bash
az monitor app-insights component create \
  --app diet-analysis-insights \
  --location eastus \
  --resource-group diet-analysis-rg \
  --application-type web

# Grab its connection string and wire it to the Function App:
INSTRUMENTATION_CONNECTION_STRING=$(az monitor app-insights component show \
  --app diet-analysis-insights \
  --resource-group diet-analysis-rg \
  --query connectionString -o tsv)

az functionapp config appsettings set \
  --name diet-analysis-func \
  --resource-group diet-analysis-rg \
  --settings APPLICATIONINSIGHTS_CONNECTION_STRING="$INSTRUMENTATION_CONNECTION_STRING"
```

Then in the Portal, open the `diet-analysis-insights` resource and check:

- **Live Metrics** — request rate/latency in real time while you click
  around the dashboard.
- **Transaction search / Traces** — the structured log fields
  (`diet_filter`, `elapsed_ms`, `k`, ...) show up as custom dimensions on
  each request, so you can filter e.g. "all `/api/clusters` calls where
  `elapsed_ms > 500`" instead of grepping text logs.
- **Failures** — any exception from the `except Exception` blocks (or the
  Blob Trigger's validation failures) appears here automatically.

This is the same three-pillar model from the observability lesson: Traces
show *where* time is spent per request, Logs (the structured fields) show
*why*, and Live Metrics is the real-time numerical view.

## 10. Verify end to end

1. Open the Static Web App URL from the Azure Portal.
2. Confirm the bar, doughnut, and scatter charts render, plus the top-5
   protein table and the nutrient correlation Heatmap (5 visualizations
   total, auto-loaded).
3. Change the diet type filter and click **Refresh** — confirm the charts
   and heatmap update and "Execution time" changes.
4. Page through **Recipes** with Previous/Next, and try the search box.
5. Drag the **Clusters (k)** slider — confirm the scatter plot and cluster
   cards recompute live; click a cluster card to isolate it.
6. Hit `/api/health` directly — confirm `{"status": "ok", ...}` with no
   Blob Storage dependency.
7. Upload a CSV to the `datasets` container and confirm `on_dataset_uploaded`
   shows an invocation in the Function App's Monitor tab (event-driven path).
8. Note the deployed URLs for the Phase 2 deliverables list:
   - Azure Function URL
   - Static Web App URL
   - GitHub repo link
   - This documentation, exported as PDF

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Dashboard shows "Failed to load data" | `API_BASE_URL` wrong, or CORS — the function already sends `Access-Control-Allow-Origin: *`, so check the URL/network tab first |
| `ModuleNotFoundError: azure.storage.blob` on deploy | `requirements.txt` didn't get picked up — redeploy with `func azure functionapp publish diet-analysis-func --build remote` |
| 500 error with "Internal error: ..." | Usually a missing/incorrect `AZURE_STORAGE_CONNECTION_STRING` app setting — re-run step 4 |
| Empty charts, no error | Check `BLOB_CONTAINER_NAME` / `BLOB_NAME` app settings match what you uploaded in step 2 |
| `ModuleNotFoundError: sklearn` on `/api/clusters` | Same cause as the `azure.storage.blob` case above — redeploy with `--build remote` so `scikit-learn` gets installed |
| `/api/clusters` slow on first request | Normal cold-start cost of loading scikit-learn on the Consumption plan; subsequent requests are fast |
