# Project Structure and File Guide

## What this project does

This repository contains a patent invention analysis service and a web portal around it. A user uploads an invention disclosure (IDF). The analysis service turns it into structured invention features, creates search terms, finds relevant CPC classifications, generates USPTO and Espacenet queries, searches non-patent literature (NPL), and creates a DOCX report.

The portal is a separate React and Django application. React provides the browser interface; Django manages organizations, users, customers, invention records, uploaded versions, and report downloads. Django calls the existing FastAPI analysis service to process an uploaded IDF.

```text
Browser
  React (web_portal/frontend)
      │ /api requests
      ▼
  Django (web_portal)
      │ POST /predict with IDF file
      ▼
  FastAPI (app.py)
      │
      ▼
  LangGraph workflow (graph/)
      ├── LLM and CPC vector search
      ├── scholarly/NPL providers
      └── DOCX report generation
```

## Main runtime flow

1. `web_portal/frontend/src/main.jsx` renders the user interface and handles navigation.
2. `web_portal/frontend/src/api.js` sends authenticated requests to Django. During local development, Vite forwards `/api` requests to Django.
3. Django routes authentication requests to `web_portal/accounts/` and customer/invention requests to `web_portal/patents/`.
4. The patents API saves an uploaded IDF as an invention version and calls FastAPI at `/predict`.
5. `app.py` invokes the graph built by `graph/graph_builder.py`; `bootstrap/bootstrap.py` initializes the shared application services at FastAPI startup.
6. The graph nodes in `graph/nodes.py` decompose the invention, generate keywords, retrieve/rank CPC candidates, and build patent search queries. `graph/npl_search.py` searches Semantic Scholar, OpenAlex, OpenAIRE and arXiv; Google Scholar through SerpApi is optional and disabled unless enabled in the process environment.
7. `services/report_service.py` creates the DOCX report. Django stores the analysis result and makes the report available to an authorized portal user.

## Repository map

```text
patent_agent/
├── app.py
├── bootstrap/
├── config/
├── graph/
├── ingestion/
├── input/
├── models/
├── other_files/
├── services/
├── web_portal/
├── ARCHITECTURE_flow.md
├── PROJECT_STRUCTURE.md
├── README_npl.md
├── README_portal.md
├── requirements.txt
├── run_project.ps1
└── setup.py
```

## Root files

| File | Purpose |
|---|---|
| `app.py` | FastAPI application entry point. Initializes the application context on startup and exposes `/health` and `/predict`. |
| `requirements.txt` | Pinned Python dependencies for the analysis service and LangGraph application. |
| `web_portal/requirements.txt` | Django portal dependencies, including the PostgreSQL driver and Gunicorn. |
| `run_project.ps1` | Starts Ollama, FastAPI, Django, and the Vite development server in separate PowerShell windows. |
| `setup.py` | A collection of local setup and run notes/commands. It is not the Python package build configuration. |
| `README_portal.md` | Portal architecture, setup, and React-to-Django request-flow notes. |
| `README_npl.md` | NPL provider behavior, configuration, and interpretation notes. |
| `ARCHITECTURE_flow.md` | Broader workflow and deployment architecture notes, including ideas for future production deployment. |
| `PROJECT_STRUCTURE.md` | This guide to the folders and files. |
| `.gitignore` | Git ignore patterns for local settings, secrets, generated data, build output, and developer files. |

## Analysis service

### `bootstrap/`

| File | Purpose |
|---|---|
| `bootstrap/bootstrap.py` | Creates the long-lived application context: LLM, embeddings, CPC Chroma vector store, graph, audit service, and report service. |

### `config/`

| File | Purpose |
|---|---|
| `config/config.py` | Local application settings and the `ApplicationContext`/request data models. This file is ignored by Git in this repository; keep credentials out of committed documentation and source. |
| `config/state.py` | LangGraph state and runtime type definitions, including invention features, CPC results, patent queries, and NPL results. |
| `config/state_old.py` | Older state definition retained for reference. |
| `config/__init__.py` | Marks `config` as a Python package. |

### `graph/`

| File | Purpose |
|---|---|
| `graph/graph_builder.py` | Defines and compiles the active LangGraph workflow: decompose → keywords → CPC lookup → USPTO query → Espacenet query → NPL search → report. |
| `graph/nodes.py` | Implements the main analysis nodes, including invention decomposition, keyword generation, CPC retrieval/ranking, patent query generation, and report invocation. |
| `graph/npl_search.py` | Active asynchronous NPL provider integration. Normalizes and deduplicates records, ranks them, and reports per-provider status. SerpApi Google Scholar is opt-in. |
| `graph/graph_builder_old.py` | Earlier graph workflow, retained for reference. |
| `graph/npl_search_old.py` | Earlier NPL search implementation, retained for reference. |

### `models/`

| File | Purpose |
|---|---|
| `models/patent_models.py` | Pydantic schemas for invention features, keywords, CPC candidates, and USPTO/Espacenet search queries. |
| `models/suspect_cpc_models.py` | Experimental/older CPC record schema. |
| `models/suspect_model.py` | Experimental helper for creating an LLM instance outside the main bootstrap path. |

### `services/`

| File | Purpose |
|---|---|
| `services/report_service.py` | Active DOCX report generator. Adds the analysis sections, NPL results, provider diagnostics, methodology, and traceability. |
| `services/report_service_old.py` | Earlier report generator, retained for reference. |
| `services/utils.py` | SQLAlchemy audit database setup and audit logging for model/tool calls. |
| `services/suspect_embedding_service.py` | Initializes the Hugging Face sentence-transformer embedding model used by the current bootstrap. |
| `services/suspect_generate_spec.py` | Separate experimental patent-specification and claims drafting workflow. |
| `services/patents_downloading/download_pipeline.py` | Standalone script for downloading and extracting patent text from Google Patents pages; separate from the current portal analysis request path. |
| `services/patentability_check/patentability_analyzer.py` | Standalone rule/LLM-based patentability and specification checks that can create a separate report. |
| `services/patentability_check/patentability_rules.py` | Rule definitions consumed by the standalone patentability checker. |
| `services/__init__.py` | Marks `services` as a Python package. |

## Web portal (`web_portal/`)

### Django project configuration: `web_portal/portal_config/`

| File | Purpose |
|---|---|
| `portal_config/settings.py` | Django settings, SQLite/PostgreSQL selection through `DATABASE_URL`, media/report paths, security, and FastAPI connection settings. |
| `portal_config/urls.py` | Top-level routing for Django admin, health/CSRF, account APIs, and patent APIs. |
| `portal_config/wsgi.py` | WSGI entry point for compatible deployment servers. |
| `portal_config/asgi.py` | ASGI entry point for ASGI deployment servers. |
| `portal_config/__init__.py` | Marks the Django project configuration as a Python package. |

### Accounts application: `web_portal/accounts/`

| File | Purpose |
|---|---|
| `accounts/models.py` | Defines `Organization` and the custom `PortalUser` associated with an organization. |
| `accounts/api.py` | Handles sign-in/out, current-user lookup, CSRF, health, and password-reset APIs. |
| `accounts/urls.py` | Maps account API paths to account handlers. |
| `accounts/admin.py` | Registers and customizes organization and user management in Django admin. |
| `accounts/apps.py` | Django application configuration. |
| `accounts/migrations/0001_initial.py` | Initial database schema migration for accounts. |
| `accounts/migrations/__init__.py` | Marks migrations as a Python package. |
| `accounts/__init__.py` | Marks the accounts app as a Python package. |

### Patent portal application: `web_portal/patents/`

| File | Purpose |
|---|---|
| `patents/models.py` | Defines customer, invention, and invention-version records, including upload and analysis/report fields. |
| `patents/api.py` | Provides customer/invention APIs, validates IDF uploads, invokes FastAPI, records analysis status/results, and serves reports. |
| `patents/urls.py` | Maps customer, invention, version, and report paths to patent API handlers. |
| `patents/admin.py` | Django admin configuration for customer, invention, and version records. |
| `patents/apps.py` | Django application configuration. |
| `patents/migrations/0001_initial.py` | Initial database schema migration for patent portal records. |
| `patents/migrations/__init__.py` | Marks migrations as a Python package. |
| `patents/__init__.py` | Marks the patents app as a Python package. |

### React frontend: `web_portal/frontend/`

| File | Purpose |
|---|---|
| `frontend/index.html` | HTML page Vite serves; contains the React mount element. |
| `frontend/package.json` | Frontend package metadata, dependencies, and Vite commands. |
| `frontend/package-lock.json` | Locks exact npm dependency versions. |
| `frontend/vite.config.js` | Configures Vite and its development proxy to Django. |
| `frontend/src/main.jsx` | React application entry point, routes, authentication context, screens, forms, and page behavior. |
| `frontend/src/api.js` | Shared browser API helper for Django requests, cookies, CSRF, and JSON error handling. |
| `frontend/src/styles.css` | Portal layout, typography, controls, tables, and responsive styling. |

### Other portal files

| File | Purpose |
|---|---|
| `web_portal/manage.py` | Django command-line entry point (`migrate`, `createsuperuser`, `runserver`, etc.). |
| `web_portal/.env.example` | Example portal environment variables; contains placeholders, not production credentials. |
| `web_portal/nginx.conf.example` | Example Nginx reverse-proxy configuration for the built frontend and backend services. |
| `web_portal/templates/registration/password_reset_email.html` | HTML password-reset email body. |
| `web_portal/templates/registration/password_reset_subject.txt` | Password-reset email subject template. |

## CPC ingestion and search utilities (`ingestion/`)

| File | Purpose |
|---|---|
| `ingestion/1-cpc_to_csv.py` | Extracts CPC definition XML into a CSV for vector-store ingestion. |
| `ingestion/2_cpc_full_ingestion.py` | Embeds CSV records and writes them to a persistent Chroma collection. |
| `ingestion/cpc_extracted_data.csv` | Intermediate/extracted CPC dataset used by ingestion workflows. |
| `ingestion/old_cpc_parser.py` | Earlier, more detailed CPC XML parsing, normalization, and validation implementation. |
| `ingestion/old_cpc_ingest.py` | Earlier end-to-end CPC normalization and Chroma ingestion workflow. |
| `ingestion/read_raw_text.py` | Small inspection utility for viewing raw CPC XML text. |
| `ingestion/check_collection.py` | Opens a Chroma collection and prints whether it exists and its record count. |
| `ingestion/audit_db.py` | Manual Chroma collection inspection/audit utility. |
| `ingestion/delete_cpc_collection.py` | Deletes the configured CPC Chroma collection; destructive maintenance utility. |
| `ingestion/test_cpc_db.py` | Experimental CPC retrieval/reranking engine for manual search evaluation. |

## Inputs, requirements, and reference material

### `input/`

| File | Purpose |
|---|---|
| `input/idf_file.txt` | Sample invention disclosure input. |
| `input/provisional_specification.pdf` | Sample provisional patent specification. |
| `input/US12736584B2.txt` | Example patent text input. |
| `input/US_20250270010_A1.txt` | Example patent publication text input. |
| `input/202521087280.txt` | Example patent/application text input. |

### `other_files/requirements/`

| File | Purpose |
|---|---|
| `requirements.md` | Earlier high-level requirements notes. |
| `requirements2.md` | Additional requirements notes. |
| `requirements3_NPL.md` | NPL-specific requirements and provider notes. |
| `wire_frames.drawio` | Current portal wireframes and requirements reference. |
| `home_page.drawio` | Home-page layout/flow diagram. |
| `login_page.drawio` | Login-page layout/flow diagram. |
| `high_lvl_rqmts.xlsx` | High-level requirements spreadsheet. |
| `~$high_lvl_rqmts.xlsx` | Temporary Microsoft Excel lock file; not a source requirements document. |

### `other_files/references/` and other retained material

| File | Purpose |
|---|---|
| `other_files/references/summary_PatenTEB.txt` | Text notes/reference material about PatenTEB. |
| `other_files/references/PatenTEB.pdf` | PDF reference about PatenTEB. |
| `other_files/pdf_service_old.py` | Earlier PDF-service implementation, retained outside the active `services/` package. |

## Local/runtime files and notes

The following are created or used at runtime and may not appear in the source inventory until the application is run:

- `data/chroma_db/full_cpc_db/`: persistent CPC Chroma vector collection.
- `data/reports/`: generated DOCX analysis reports.
- `data/portal_media/`: uploaded IDF documents managed by Django.
- `patent_agent.db`: SQLite audit database created by `services/utils.py`.
- `web_portal/portal.sqlite3`: default Django database; PostgreSQL can be selected with `DATABASE_URL`.
- `web_portal/frontend/node_modules/` and `web_portal/frontend/dist/`: npm dependencies and production build output.

`README.md` and `config/config.py` are currently ignored by Git in this workspace. The former contains local workflow/design notes; the latter contains local settings. Avoid placing secrets in documentation, and keep local credentials out of source control.

Files ending in `_old.py` are retained earlier versions, not the active graph/report/NPL implementations. Files prefixed with `suspect_` are prototypes or supporting experiments, except `services/suspect_embedding_service.py`, which is currently imported by the active bootstrap.
