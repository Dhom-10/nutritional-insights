# Phase 2 — Cloud Dashboard Development

Builds on Phase 1 (`github.com/Dhom-10/nutritional-insights`): moves the
diet-analysis Azure Function from local Azurite to real Azure Blob
Storage, and adds a browser dashboard that visualizes the results.

## Structure

```
Phase2_Cloud_Dashboard/
├── azure-function/
│   ├── function_app.py           # HTTP-triggered Azure Function (Python v2 model)
│   ├── requirements.txt
│   ├── host.json
│   ├── local.settings.json.example
│   ├── upload_dataset_to_cloud.py  # uploads All_Diets.csv to real Azure Blob Storage
│   └── .gitignore
├── dashboard/
│   ├── index.html                # single-file dashboard (Chart.js via CDN)
│   └── staticwebapp.config.json
└── docs/
    ├── DEPLOYMENT_GUIDE.md       # step-by-step Azure deployment instructions
    └── Phase2_Documentation.pdf  # architecture, workflow, and challenges write-up
```

## Endpoints

- `GET /api/insights` — average macros, top-5 protein recipes per diet,
  highest-protein diet, most common cuisine per diet, execution time (ms)
- `GET /api/insights?diet_type=keto` — same, filtered to one diet type
- `GET /api/diet_types` — distinct diet types, used to populate the
  dashboard's filter dropdown

## Quick start

1. `cd azure-function && cp local.settings.json.example local.settings.json`
   and fill in your Azure Storage connection string
2. `pip install -r requirements.txt && func start`
3. Open `dashboard/index.html` in a browser (it defaults to
   `http://localhost:7071/api`)

For full cloud deployment (Function App, Blob Storage, Static Web App),
see `docs/DEPLOYMENT_GUIDE.md`.
