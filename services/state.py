"""
/**
* ? Author: Gautam
* ? Date: 2026-02-20
* ? Description:  this file is responsible for bootstrapping the application by initializing the necessary components and creating the application context. It sets up the LLM, embeddings, vector store, runtime, checkpointer, graph, and audit service based on the provided settings. The ApplicationBootstrap class provides a build method that returns an instance of ApplicationContext containing all the initialized components.
* ? Usage:  The ApplicationBootstrap class can be used to create an instance of ApplicationContext
*/
"""

import operator
from typing import Annotated, Any, Optional

from openai import BaseModel
from models.patent_models import InventionRepresentation, KeywordAnalysis, CPCAnalysis
from typing_extensions import TypedDict


# from typing_extensions import TypedDict


class PatentState(TypedDict, total=False):
    session_id: str
    idf_text: str
    invention: InventionRepresentation
    pdf_path: str
    keywords: KeywordAnalysis
    report_path: str
    cpc_analysis: CPCAnalysis


class RuntimeContext(TypedDict):
    llm: object
    retriever: object
    account_tool: object


class IntentResult(BaseModel):
    intent: str
    confidence: float


class GraphState(TypedDict):
    intent: str | None
    confidence: float

    # Guardrail results
    is_safe_query: bool
    guardrail_feedback: str | None

    # Parallel destination targets (safe if distinct, but explicitly typed here)
    account_data: dict | None
    rag_context: list[Any] | None  # Adjust to List[Document] depending on your retriever output

    # CRITICAL FIX: If parallel branches track tool counts or usage concurrently,
    # you MUST use operator.add so they sum together instead of overwriting each other!
    tool_calls: Annotated[int, operator.add]
    token_usage: Annotated[int, operator.add]

    max_tool_calls: int
