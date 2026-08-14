"""
/**
* ? Author: Gautam
* ? Date: 2026-02-20
* ? Description:  this file is for configuration of the application, including environment variables, settings, and application context.
*/
"""

import os
from dataclasses import dataclass

from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from services.utils import AuditService


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
    # os.environ.setdefault(
    #     "LANGSMITH_API_KEY", "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"
    # )
    # os.environ["HUGGINGFACEHUB_API_TOKEN"] = (
    #     "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"  # gg-test-15-02 )
    # )


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


class PredictRequest(BaseModel):
    question: str
    session_id: str
