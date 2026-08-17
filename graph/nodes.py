"""
/**
* ? Author: Gautam
* ? Date: 2026-07-14
* ? Description:  file has acutually the nodes for the graph, defining the logic for intent routing, RAG decision-making, and parallel execution. It includes functions for fast intent routing, LLM-based intent routing, and conditional routing based on confidence scores. The nodes are designed to be used within the state graph built in graph_builder.py.
* ? Usage:  graph_builder.py imports this file to access the node functions when constructing the state graph for the application.
*/
"""

import inspect
from services.state import PatentState
from models.patent_models import InventionRepresentation, KeywordAnalysis
from langchain_core.runnables import RunnableConfig

from config.config import ApplicationContext, Settings


DECOMPOSE_PROMPT = """
You are a patent invention analysis assistant.

Your task is to analyze an Invention Disclosure Form (IDF) and
convert the invention into a structured technical representation.

Separate the invention into exactly three categories:

1. Structural features
   - Physical components
   - System components
   - Sensors
   - Modules
   - Data/storage components
   - Communication components
   - Relationships between components

2. Procedural/process features
   - Operational steps
   - Sequence of operations
   - Data processing steps
   - Detection/measurement steps
   - Decision steps
   - Control/adaptation steps

3. Functional features
   - What the invention does
   - Technical capabilities
   - Technical effects/functions
   - Relationships between inputs and resulting functions

IMPORTANT:

- Extract information from the IDF.
- Do not invent technical features that are not reasonably supported
  by the IDF.
- Preserve technically meaningful details.
- Do not classify a function merely as structural.
- Do not classify a physical component merely as a function.
- A feature may have relationships with other features.
- Separate distinct technical features rather than combining everything
  into one large statement.
- Assign stable IDs:
    Structural: SF-01, SF-02, ...
    Procedural: PF-01, PF-02, ...
    Functional: FF-01, FF-02, ...
"""

KEYWORDS_PROMPT = """
You are a patent prior-art search strategist.

Your task is to analyze a structured representation of an invention
and generate terminology that can be used to search patent literature.

For EACH feature:

1. Identify the primary technical keywords.
2. Identify technically meaningful synonyms.
3. Identify alternative terminology commonly used in patents.

IMPORTANT:

- Focus on technically meaningful terminology.
- Prefer patent/technical terminology over generic English words.
- Do not generate unrelated words merely because they are semantically similar.
- Preserve the meaning of the original feature.
- Do not introduce technical concepts that are not supported by the feature.
- Include singular/plural variants only when useful.
- Include abbreviations where they are commonly used.
- Include terminology that a patent examiner or patent practitioner
  might reasonably encounter.

Generate keywords independently for:
- Structural features
- Procedural/process features
- Functional features

Then create a consolidated list containing the most useful
unique search terms across all three categories.

The feature_id MUST be preserved exactly.
"""


def decompose_invention(state: PatentState, config: RunnableConfig) -> dict:
    idf_text = state["idf_text"]
    configurable = config.get("configurable", {})
    context = configurable.get("context")
    thread_id = configurable.get("thread_id")
    audit = context.audit
    llm = context.llm
    if not llm:
        raise ValueError("LLM instance was not passed in the runtime config.")
    structured_llm = llm.with_structured_output(InventionRepresentation)

    prompt = f"""
    {DECOMPOSE_PROMPT}
    Analyze the following IDF.
    --- IDF START ---
    {idf_text}
    --- IDF END ---
    """
    result = structured_llm.invoke(prompt)
    function_name = inspect.currentframe().f_code.co_name
    audit.log_model_call(thread_id, function_name, state["idf_text"], result)

    return {"invention": result}


def create_invention_pdf(state: PatentState, config: RunnableConfig):
    configurable = config.get("configurable", {})
    context = configurable.get("context")

    pdf_path = context.pdf_service.create_invention_pdf(
        session_id=state["session_id"],
        invention=state["invention"],
    )
    return {"pdf_path": pdf_path}


def generate_keywords(state: PatentState, config: RunnableConfig) -> dict:

    configurable = config.get("configurable", {})
    context = configurable.get("context")
    thread_id = configurable.get("thread_id")
    audit = context.audit
    llm = context.llm

    if not llm:
        raise ValueError("LLM instance was not passed in the runtime config.")

    invention = state["invention"]
    structured_llm = llm.with_structured_output(KeywordAnalysis)
    prompt = f"""
    {DECOMPOSE_PROMPT}
    Here is the structured representation of the invention:
    --- INVENTION SUMMARY ---
    {invention.invention_summary}
    --- STRUCTURAL FEATURES ---
    {invention.structural_features}
    --- PROCEDURAL FEATURES ---
    {invention.procedural_features}
    --- FUNCTIONAL FEATURES ---
    {invention.functional_features}
    """
    result = structured_llm.invoke(prompt)
    function_name = inspect.currentframe().f_code.co_name
    audit.log_model_call(thread_id, function_name, prompt, result)
    print("THIS IS THE RESULT FROM KEYWORDS NODE {result}")
    return {"keywords": result}
