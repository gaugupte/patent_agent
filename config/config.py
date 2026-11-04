"""
/**
* ? Author: Gautam
* ? Date: 2026-02-20
* ? Description:  this file is for configuration of the application, including environment variables, settings, and application context.
*/
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from services.utils import AuditService
from other_files.pdf_service_old import PDFService


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)


class Settings:
    # ============================================================
    # Environment Configuration
    # ============================================================

    def __init__(self):
        # self.app_name = "LangAgent"
        # self.version = "1.0.0"
        # self.debug = True
        # self.host = ""
        ## !!! IMPORTANT: Replace with actual PostgreSQL connection string !!!
        DB_URL = os.getenv("DB_URL", "mongodb://localhost:27017")

    # Handling Data Types: os.getenv ALWAYS returns a string. # You must manually convert types for integers and booleans.
    PORT = int(os.getenv("PORT", "3000"))
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGCHAIN_PROJECT", "lg-template")
    os.environ.setdefault("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    os.environ.setdefault("CROSSREF_MAILTO", "")
    #
    os.environ.setdefault("ENABLE_SERPAPI_GOOGLE_SCHOLAR", "true")


@dataclass
class ApplicationContext:
    settings: object
    llm: object
    embeddings: object
    vector_store: object
    retriever: object
    runtime: object
    checkpointer: object
    graph: CompiledStateGraph
    audit: AuditService
    db_engine: object  # Add this line to include the database engine in the context
    report_service: PDFService


class PredictRequest(BaseModel):
    question: str
    session_id: str
