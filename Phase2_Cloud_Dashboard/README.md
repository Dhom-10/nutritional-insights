# Phase 2 — Cloud Dashboard Development

Builds on Phase 1 (`github.com/Dhom-10/nutritional-insights`): moves the
diet-analysis Azure Function from local Azurite to real Azure Blob
Storage, and adds a browser dashboard that visualizes the results.

## Structure

```
Phase2_Cloud_Dashboard/
├── azure-function/
│   ├── function_app.py
│   ├── requirements.txt
│   ├── host.json
│   ├── local.settings.json.example
│   ├── upload_dataset_to_cloud.py
│   └── .gitignore
├── dashboard/
│   ├── index.html
│   └── staticwebapp.config.json
└── docs/
    ├── DEPLOYMENT_GUIDE.md
    └── Phase2_Documentation.pdf
```

## Endpoints

- `GET /api/insights` — average macros, top-5 protein recipes per diet,
  highest-protein diet, most common cuisine per diet, execution time (ms)
- `GET /api/insights?diet_type=keto` — same, filtered to one diet type
- `GET /api/diet_types` — distinct diet types, used to populate the
  dashboard's filter dropdown
- `GET /api/correlations` (`?diet_type=keto`) — Protein/Carbs/Fat
  correlation matrix, powers the dashboard's nutrient correlation Heatmap
- `GET /api/recipes` (`?diet_type=keto&page=2&page_size=10`) — paginated
  individual recipe rows, powers the "Get Recipes" button + pagination UI
- `GET /api/clusters` (`?diet_type=keto&k=4`) — K-Means clustering of
  recipes by macronutrient profile, powers the "Get Clusters" button

## Quick start

1. `cd azure-function && cp local.settings.json.example local.settings.json`
   and fill in your Azure Storage connection string
2. `pip install -r requirements.txt && func start`
3. Open `dashboard/index.html` in a browser (it defaults to
   `http://localhost:7071/api`)

Alternatively, for local testing without Azure Functions Core Tools at
all, run `python mockapi/server.py path/to/All_Diets.csv` — it serves the
same routes on `http://localhost:7071/api/...` using the exact analysis
functions from `azure-function/function_app.py`.

For full cloud deployment (Function App, Blob Storage, Static Web App),
see `docs/DEPLOYMENT_GUIDE.md`.
