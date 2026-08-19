"""
/**
* ? Author: Gautam
* ? Date: 2026-07-14
* ? Description:  file has acutually the nodes for the graph, defining the logic for intent routing, RAG decision-making, and parallel execution. It includes functions for fast intent routing, LLM-based intent routing, and conditional routing based on confidence scores. The nodes are designed to be used within the state graph built in graph_builder.py.
* ? Usage:  graph_builder.py imports this file to access the node functions when constructing the state graph for the application.

One improvement I'd make now

For a production patent product, I would eventually make the LLM output more explicit:

CPC
├── relevance: HIGH / MEDIUM / LOW
├── matched_features: [SF-02, FF-01]
├── technical_basis: ...
└── confidence: ...

That gives us a much better audit trail for why a CPC was selected.
*/
"""

import inspect
from services.state import PatentState
from models.patent_models import InventionRepresentation, KeywordAnalysis, CPCAnalysis
from langchain_core.runnables import RunnableConfig

from config.config import ApplicationContext, Settings

# from services.report_service import create_client_report

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

CPC_SYSTEM_PROMPT = """
You are a patent classification specialist.

Your task is to identify CPC classifications that are useful
for further patent prior-art searching.

You have been provided with:
1. The structured representation of the invention.
2. Technical keywords generated for the invention.
3. CPC classifications retrieved from the official CPC 2026.08 corpus.

IMPORTANT RULES:

1. Select CPC codes ONLY from the supplied candidate list.
2. Never invent or modify a CPC code.
3. Evaluate candidates against the actual technical features
   of the invention, not merely keyword overlap.
4. Consider structural, procedural/process and functional
   aspects of the invention.
5. Do not require a CPC to cover the entire invention.
   A CPC covering an important technical aspect may be useful.
6. Retain secondary CPCs when they could reasonably improve
   the subsequent patent search.

RELEVANCE:

HIGH:
Directly covers an important technical aspect of the invention.

MEDIUM:
Covers an important component, function, process or technical
relationship, but is not the primary classification.

LOW:
Has a weaker but potentially useful technical relationship
and may be retained for broader searching.

Return the strongest useful CPC candidates.

Prefer approximately 5–15 CPC classifications when the
candidate pool supports them.

For every selected CPC:
- provide the CPC code exactly as supplied
- identify the associated invention feature(s)
- assign HIGH, MEDIUM or LOW relevance
- explain the technical basis briefly
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


def lookup_cpc(state: PatentState, config: RunnableConfig) -> dict:

    configurable = config.get("configurable", {})
    context = configurable.get("context")
    thread_id = configurable.get("thread_id")

    if context is None:
        raise ValueError("Application context was not passed in runtime config.")

    llm = context.llm
    audit = context.audit
    cpc_vector_store = context.vector_store

    if llm is None:
        raise ValueError("LLM instance is not available.")

    if cpc_vector_store is None:
        raise ValueError("CPC vector store is not available.")

    keyword_analysis = state["keywords"]

    # ---------------------------------------------------------
    # 1. Build independent queries for each feature
    # ---------------------------------------------------------

    queries = []

    for item in keyword_analysis.structural_keywords:
        query = " ".join(
            [
                item.feature,
                *item.primary_keywords,
                *item.synonyms,
                *item.alternative_terms,
            ]
        )

        queries.append(
            {
                "feature_id": item.feature_id,
                "category": "structural",
                "query": query,
            }
        )
    print(f" These are structure keys {queries}")
    for item in keyword_analysis.procedural_keywords:
        query = " ".join(
            [
                item.feature,
                *item.primary_keywords,
                *item.synonyms,
                *item.alternative_terms,
            ]
        )

        queries.append(
            {
                "feature_id": item.feature_id,
                "category": "procedural",
                "query": query,
            }
        )

    for item in keyword_analysis.functional_keywords:
        query = " ".join(
            [
                item.feature,
                *item.primary_keywords,
                *item.synonyms,
                *item.alternative_terms,
            ]
        )

        queries.append(
            {
                "feature_id": item.feature_id,
                "category": "functional",
                "query": query,
            }
        )

    # ---------------------------------------------------------
    # 2. Search Chroma
    # ---------------------------------------------------------

    candidates = {}

    for item in queries:
        documents = cpc_vector_store.similarity_search(
            item["query"],
            k=20,
        )

        for doc in documents:
            cpc_code = doc.metadata.get("cpc_code")

            if not cpc_code:
                continue

            # Keep one record for each CPC.
            # Preserve all associated feature IDs.
            if cpc_code not in candidates:
                candidates[cpc_code] = {
                    "cpc_code": cpc_code,
                    "title": doc.page_content,
                    "feature_ids": [item["feature_id"]],
                }

            else:
                if item["feature_id"] not in candidates[cpc_code]["feature_ids"]:
                    candidates[cpc_code]["feature_ids"].append(item["feature_id"])

    # ---------------------------------------------------------
    # 3. Consolidated keyword search
    # ---------------------------------------------------------

    consolidated_query = " ".join(keyword_analysis.consolidated_keywords)

    consolidated_documents = cpc_vector_store.similarity_search(
        consolidated_query,
        k=30,
    )

    for doc in consolidated_documents:
        cpc_code = doc.metadata.get("cpc_code")

        if not cpc_code:
            continue

        if cpc_code not in candidates:
            candidates[cpc_code] = {
                "cpc_code": cpc_code,
                "title": doc.page_content,
                "feature_ids": [],
            }

    # ---------------------------------------------------------
    # 4. Prepare candidates for LLM
    # ---------------------------------------------------------

    candidate_text = ""

    for candidate in candidates.values():
        candidate_text += f"""
    CPC CODE:
    {candidate["cpc_code"]}

    DESCRIPTION:
    {candidate["title"]}

    ASSOCIATED FEATURES:
    {", ".join(candidate["feature_ids"])}

    ----------------------------------------
    """
    # ---------------------------------------------------------
    # 5. Ask LLM to evaluate candidates
    # ---------------------------------------------------------
    prompt = f"""
    {CPC_SYSTEM_PROMPT}
    INVENTION KEYWORD ANALYSIS:
    
    {keyword_analysis.model_dump_json(indent=2)}

    CANDIDATE CPC CLASSIFICATIONS:

    {candidate_text}

    Select the CPC classifications that are genuinely relevant.
    """

    structured_llm = llm.with_structured_output(CPCAnalysis)

    result = structured_llm.invoke(prompt)

    # ---------------------------------------------------------
    # 6. Audit
    # ---------------------------------------------------------
    function_name = inspect.currentframe().f_code.co_name
    audit.log_model_call(
        thread_id,
        function_name,
        prompt,
        result,
    )
    return {"cpc_analysis": result}  # 7. Return to LangGraph state


# ************************************************************************************************************************************
# create_client_report_node: report printing
# ************************************************************************************************************************************


def create_client_report(
    state: PatentState,
    config: RunnableConfig,
) -> dict:

    configurable = config.get("configurable", {})
    context = configurable.get("context")
    thread_id = configurable.get("thread_id")
    if context is None:
        raise ValueError("Application context was not passed in runtime config.")
    report_path = context.report_service.create_client_report(
        state=state,
        session_id=thread_id,
    )
    return {"report_path": report_path}
