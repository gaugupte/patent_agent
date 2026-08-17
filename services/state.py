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
from models.patent_models import InventionRepresentation
from typing_extensions import TypedDict

from models.patent_models import KeywordAnalysis
# from typing_extensions import TypedDict


class PatentState(TypedDict, total=False):
    session_id: str
    idf_text: str
    invention: InventionRepresentation
    pdf_path: str
    keywords: KeywordAnalysis


class RuntimeContext(TypedDict):
    llm: object
    retriever: object
    account_tool: object


class IntentResult(BaseModel):
    intent: str
    confidence: float


class GraphState(TypedDict):
    question: str
    session_id: str
    answer: str
    query: str
    intent: str | None
    confidence: float

    # Guardrail results
    is_safe_query: bool
    guardrail_feedback: str | None

    # Parallel destination targets (safe if distinct, but explicitly typed here)
    account_data: dict | None
    rag_context: (
        list[Any] | None
    )  # Adjust to List[Document] depending on your retriever output

    # CRITICAL FIX: Add explicit fields for the errors your parallel nodes return
    account_error: str | None
    rag_error: str | None

    # CRITICAL FIX: If parallel branches track tool counts or usage concurrently,
    # you MUST use operator.add so they sum together instead of overwriting each other!
    tool_calls: Annotated[int, operator.add]
    token_usage: Annotated[int, operator.add]

    requires_rag: bool
    requires_guardrails: bool
    latency_budget: float
    token_budget: int
    max_tool_calls: int
    response: str | None

    # Safe multi-branch tracking using our custom dictionary reducer
    # telemetry: Annotated[Dict[str, Any], merge_dicts]
