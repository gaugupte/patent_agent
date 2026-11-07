from openpyxl import Workbook
from pathlib import Path

backend = [
    ['B-01','Backend','Must','Accept an IDF file upload through the FastAPI /predict endpoint.','app.py; config/state.py','Supports UTF-8 text input and session-based execution.'],
    ['B-02','Backend','Must','Decompose the invention into structural, procedural, and functional features.','graph/nodes.py; models/patent_models.py','Each feature has a stable identifier.'],
    ['B-03','Backend','Must','Generate technical keywords, synonyms, and alternative search terms.','graph/nodes.py; models/patent_models.py','Used to support patent search queries.'],
    ['B-04','Backend','Must','Select relevant CPC classifications from the CPC dataset.','graph/nodes.py; models/patent_models.py','Candidates include code, title, relevance, and reason.'],
    ['B-05','Backend','Must','Generate USPTO search queries in TITLE, DESCRIPTION, CLAIMS, and CPC formats.','graph/nodes.py; models/patent_models.py','Searches are constructed from keyword and CPC analysis.'],
    ['B-06','Backend','Must','Generate Espacenet search queries with purpose and priority metadata.','graph/nodes.py; models/patent_models.py','Used alongside USPTO search strategy.'],
    ['B-07','Backend','Must','Search non-patent literature across Semantic Scholar, OpenAlex, OpenAIRE, and arXiv.','README_npl.md; graph/npl_search.py','Optional SerpApi support for Google Scholar.'],
    ['B-08','Backend','Should','Normalize, deduplicate, and rerank NPL results for human review.','README_npl.md; graph/npl_search.py','LLM reranking is used as a triage aid.'],
    ['B-09','Backend','Must','Maintain per-session LangGraph state and execution context.','app.py; config/state.py; graph/graph_builder.py','Thread/session IDs preserve state across runs.'],
    ['B-10','Backend','Must','Create a DOCX patent report with executive summary, analysis, queries, references, and traceability.','services/report_service.py','Report is generated after the graph completes.'],
    ['B-11','Backend','Must','Use an LLM via Ollama/OpenAI-compatible interface.','bootstrap/bootstrap.py','Base URL and model are configured via environment variables.'],
    ['B-12','Backend','Must','Store and retrieve CPC embeddings using Chroma vector search.','bootstrap/bootstrap.py','Vector storage supports classification retrieval.'],
    ['B-13','Backend','Must','Handle transient failures with retry and fallback logic.','graph/graph_builder.py; README_npl.md','Retry policy and fallback are built into the workflow.'],
    ['B-14','Backend','Must','Keep AI-generated results separate from legal novelty or patentability conclusions.','README_npl.md','Human review is required for any legal judgment.'],
]

portal = [
    ['P-01','Portal','Must','Provide a Django web application with organizations, users, authentication, and admin access.','web_portal/README.md; web_portal/accounts/models.py; web_portal/portal_config/settings.py','Portal is separate from the backend API.'],
    ['P-02','Portal','Must','Support organization-scoped user access and active subscription/trial checks.','web_portal/accounts/api.py; web_portal/accounts/models.py','Users cannot access the portal unless their org is active and account is allowed.'],
    ['P-03','Portal','Must','Reject duplicate concurrent sessions and enforce a single active portal session per user.','web_portal/accounts/api.py; web_portal/accounts/models.py','Single session enforcement is explicit.'],
    ['P-04','Portal','Must','Support username/password login, email-code login, and external identity sign-in.','web_portal/accounts/api.py; web_portal/accounts/models.py','Multiple login methods are implemented.'],
    ['P-05','Portal','Must','Model organizations, plans, seat purchases, and expiry windows.','web_portal/accounts/models.py','Billing is simulated but structured as real subscription entities.'],
    ['P-06','Portal','Must','Allow creation and management of customer records within an organization.','web_portal/patents/models.py; web_portal/patents/api.py','Customers are scoped to an organization.'],
    ['P-07','Portal','Must','Allow creation of invention records and versioned analyses.','web_portal/patents/models.py; web_portal/patents/api.py','Each invention can have multiple IDF versions.'],
    ['P-08','Portal','Must','Validate uploaded IDF files: .txt only, UTF-8 only, size <= 10 MB.','web_portal/patents/api.py; web_portal/portal_config/settings.py','This is the current v1 contract.'],
    ['P-09','Portal','Must','Trigger backend analysis after each new version submission.','web_portal/patents/api.py','FastAPI analysis is invoked asynchronously from the portal.'],
    ['P-10','Portal','Must','Store analysis results and report locations against the version record.','web_portal/patents/api.py; web_portal/patents/models.py','Analysis payload and report path are persisted.'],
    ['P-11','Portal','Must','Allow download of completed reports only for authorized organization versions.','web_portal/patents/api.py','Path validation prevents traversal outside approved directories.'],
    ['P-12','Portal','Must','Keep admin and client portal access distinct.','web_portal/accounts/api.py; web_portal/README.md','Superuser accounts are excluded from the portal.'],
    ['P-13','Portal','Should','Serve the UI via React/Nginx while Django exposes API/admin services.','web_portal/README.md','Production topology expects a separate frontend.'],
    ['P-14','Portal','Should','Support secure browser behavior with CSRF, HTTP-only cookies, and trusted origins.','web_portal/portal_config/settings.py','Hardened security is enabled in production.'],
]

deployment = [
    ['D-01','Deployment','Must','Support SQLite for local development and PostgreSQL for production via DATABASE_URL.','web_portal/portal_config/settings.py; web_portal/README.md','Database choice is environment-driven.'],
    ['D-02','Deployment','Must','Store uploaded IDFs and generated reports outside the database in a persistent file store.','web_portal/portal_config/settings.py; web_portal/README.md','Persistent storage is required for scaling.'],
    ['D-03','Deployment','Must','Run FastAPI as a private backend service and do not expose it publicly.','web_portal/README.md','Production topology treats FastAPI as private-only.'],
    ['D-04','Deployment','Should','Serve the React frontend through Nginx and proxy /api/ and /admin/ requests to Django.','web_portal/README.md','This is the intended production topology.'],
    ['D-05','Deployment','Must','Use environment variables for secret keys, allowed hosts, email config, and external service endpoints.','web_portal/portal_config/settings.py','Production config expects strong environment handling.'],
    ['D-06','Deployment','Should','Support a multi-process local dev stack: FastAPI, Django, and React.','web_portal/README.md; setup.py; run_project.ps1','This matches the documented startup flow.'],
    ['D-07','Deployment','Should','Support Gunicorn for Django and Uvicorn for FastAPI in production.','web_portal/README.md','This is the documented production service model.'],
    ['D-08','Deployment','Must','Keep internal service URLs and report roots outside the browser-facing app layer.','web_portal/portal_config/settings.py; web_portal/patents/api.py','Only necessary metadata is exposed to the client.'],
]

wb = Workbook()
header = ['Requirement ID', 'Area', 'Priority', 'Requirement Statement', 'Evidence / Source', 'Notes']
for title, rows in [('Backend', backend), ('Portal', portal), ('Deployment', deployment)]:
    ws = wb.create_sheet(title)
    ws.append(header)
    for row in rows:
        ws.append(row)
    for col in ['A', 'B', 'C', 'D', 'E', 'F']:
        ws.column_dimensions[col].width = 30
    ws.freeze_panes = 'A2'

if 'Sheet' in wb.sheetnames:
    wb.remove(wb['Sheet'])

out_path = Path(r'E:\Gautam\work_folder\own\nlp\patent_agent\system_portal_deployment_requirements.xlsx')
wb.save(out_path)
print(f'Created: {out_path}')
print(f'Backend={len(backend)} Portal={len(portal)} Deployment={len(deployment)}')
