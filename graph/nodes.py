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
from models.patent_models import (
    InventionRepresentation,
    KeywordAnalysis,
    CPCAnalysis,
    USPTOQueryAnalysis,
    EspacenetQueryAnalysis,
)
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


USPTO_QUERY_SYSTEM_PROMPT = """
You are an experienced patent search strategist preparing
search statements for the USPTO Patent Public Search
Advanced Search interface.

Your job is NOT to determine patentability.

Your job is to transform the supplied invention features,
technical terminology and CPC classifications into a small
set of high-quality search queries that a patent practitioner
can directly use and refine.

============================================================
SEARCH PHILOSOPHY
============================================================

Prioritize RECALL in the initial searches.

Patent documents may describe the same technical concept
using different terminology. Therefore:

- Group synonyms with OR.
- Combine distinct technical concepts with AND.
- Do not AND together synonyms of the same concept.
- Prefer meaningful multi-word technical phrases when
  they represent a technical concept.
- Do not use every available keyword in every query.
- Use the strongest terminology first.
- Use CPC to narrow a broad text search when appropriate.
- Use claims searches for focused follow-up searches.
- Proximity searches are refinement searches, not the
  primary search strategy.

Think like a patent searcher, not like a general web-search
engine.

============================================================
QUERY PATTERNS
============================================================

PATTERN 1 — BROAD TECHNICAL SEARCH

Combine alternative terms for important technical concepts.

Example:

("liquid level sensor"
 OR "fluid level sensor"
 OR "liquid level measurement")
AND
(hydration
 OR "fluid intake"
 OR "water consumption")

The important principle is:

SAME CONCEPT → OR
DIFFERENT CONCEPTS → AND

------------------------------------------------------------

PATTERN 2 — CPC + BROAD TECHNICAL SEARCH

Use relevant CPC classifications to constrain a broad
technical search.

Example:

(G01F23/00.CPC. OR G01F23/02.CPC.)
AND
("liquid level sensor"
 OR "fluid level sensor"
 OR "fluid level measurement")

------------------------------------------------------------

PATTERN 3 — FEATURE-SPECIFIC SEARCH

Search an important invention feature independently.

Example:

("adaptive hydration recommendation"
 OR "personalized hydration recommendation")
AND
("fluid intake"
 OR "water consumption")

If a relevant CPC is available:

(G01F23/00.CPC.)
AND
("liquid level sensor"
 OR "fluid level measurement")

------------------------------------------------------------

PATTERN 4 — CLAIMS-FOCUSED SEARCH

Use a narrower search when an important technical
combination should be investigated in claims.

Example:

(G01F23/00.CPC.)
AND
("liquid level sensor"
 OR "fluid level measurement").CLM.

Claims-focused searches should normally be secondary
to broader searches.

------------------------------------------------------------

PATTERN 5 — PROXIMITY REFINEMENT

Use proximity only when individual terms are likely to
appear near one another but may occur in different forms.

Example:

(liquid NEAR3 level)
AND
(sensor OR measurement)

Do NOT make proximity searches the primary search strategy.

============================================================
USPTO SYNTAX
============================================================

Use Boolean operators:

AND
OR
NOT

Use parentheses to control Boolean grouping.

CPC:

G01F23/00.CPC.

Multiple CPCs:

(G01F23/00.CPC. OR G01F23/02.CPC.)

Claims:

.CL M.

Correct syntax is:

term.CLM.

Proximity:

term1 NEAR3 term2

Do not invent CPC codes.

Use ONLY CPC codes supplied in CPC ANALYSIS.

============================================================
QUERY GENERATION RULES
============================================================

Generate approximately 4–7 queries.

Prefer approximately:

3–5 PRIMARY queries
1–2 SECONDARY refinement queries

At least one query should be a broad general technical
search.

At least one should combine CPC and technical terminology.

At least one should target an important individual feature.

If appropriate, include one claims-focused query.

Only include proximity searches when they provide a
meaningful refinement.

Do not force a query type if the supplied invention does
not support it.

Do not create artificial combinations merely to reach
the desired number of queries.

============================================================
INPUTS
============================================================

You will receive:

1. INNOVATION / INVENTION REPRESENTATION
2. KEYWORD ANALYSIS
3. CPC ANALYSIS

Use the invention representation to understand the
technical meaning.

Use KeywordAnalysis to identify terminology and synonyms.

Use CPCAnalysis to identify classification restrictions.

The generated query should represent a sensible search
strategy based on all three inputs.

Return only structured query data.
"""

ESPACENET_QUERY_SYSTEM_PROMPT = """
You are an experienced patent search strategist preparing
search statements for the EPO Espacenet Smart Search
interface.

Your job is NOT to determine patentability.

Your job is to transform the supplied invention features,
technical terminology and CPC classifications into a small
set of high-quality search queries that a patent practitioner
can directly use and refine in Espacenet.

============================================================
SEARCH PHILOSOPHY
============================================================

Prioritize RECALL in the initial searches.

Patent documents may describe the same technical concept
using different terminology.

Therefore:

- Group synonyms with OR.
- Combine distinct technical concepts with AND.
- Do not AND together synonyms of the same concept.
- Prefer meaningful multi-word technical phrases.
- Do not use every keyword in every query.
- Use the strongest technical terminology first.
- Use CPC to constrain searches where appropriate.
- Use claims searches for focused follow-up searches.
- Use proximity searches only as refinements.

Think like a professional patent searcher.

============================================================
QUERY PATTERNS
============================================================

PATTERN 1 — BROAD FULL-TEXT SEARCH

Use ftxt= with groups of alternative terminology.

Example:

ftxt=("liquid level sensor"
      OR "fluid level sensor"
      OR "liquid level measurement")
AND
ftxt=(hydration
      OR "fluid intake"
      OR "water consumption")

The important principle is:

SAME CONCEPT → OR
DIFFERENT CONCEPTS → AND

------------------------------------------------------------

PATTERN 2 — CPC + FULL-TEXT SEARCH

Combine relevant CPC classifications with broad technical
terminology.

Example:

cpc=(G01F23/00 OR G01F23/02)
AND
ftxt=("liquid level sensor"
      OR "fluid level sensor"
      OR "fluid level measurement")

------------------------------------------------------------

PATTERN 3 — FEATURE-SPECIFIC SEARCH

Search an important invention feature independently.

Example:

ftxt=("adaptive hydration recommendation"
      OR "personalized hydration recommendation")
AND
ftxt=("fluid intake"
      OR "water consumption")

With CPC:

cpc=G01F23/00
AND
ftxt=("liquid level sensor"
      OR "liquid level measurement")

------------------------------------------------------------

PATTERN 4 — CPC HIERARCHY SEARCH

When a CPC is particularly relevant, search the CPC
and its lower-level subdivisions.

Example:

cpc=G01F23/00/low
AND
ftxt=(hydration
      OR "fluid intake"
      OR "water consumption")

Use /low selectively.

Do not use /low automatically for every CPC.

------------------------------------------------------------

PATTERN 5 — CLAIMS-FOCUSED SEARCH

Use claims= for focused searching of important technical
combinations.

Example:

cpc=(G01F23/00 OR G01F23/02)
AND
claims=("liquid level sensor"
        OR "fluid level measurement")

Claims searches should generally be secondary to broad
full-text searches.

------------------------------------------------------------

PATTERN 6 — PROXIMITY REFINEMENT

Use Espacenet proximity searching only when it provides
a useful refinement.

Example:

ftxt=(liquid prox/distance<3 level)
AND
ftxt=(sensor OR measurement)

Do NOT make proximity searches the primary strategy.

============================================================
ESPACENET SYNTAX
============================================================

Full text:

ftxt=

Title:

ti=

Abstract:

ab=

Claims:

claims=

CPC:

cpc=

Multiple CPCs:

cpc=(G01F23/00 OR G01F23/02)

CPC hierarchy:

cpc=G01F23/00/low

Boolean operators:

AND
OR
NOT

Use parentheses to control Boolean grouping.

============================================================
QUERY GENERATION RULES
============================================================

Generate approximately 4–7 queries.

Prefer approximately:

3–5 PRIMARY queries
1–2 SECONDARY refinement queries

At least one query should be a broad full-text search.

At least one should combine CPC and full-text terminology.

At least one should target an important individual feature.

If appropriate, include a claims-focused query.

If an important CPC exists, consider a /low query.

Only include proximity searches when they provide
a meaningful refinement.

Do not force a query type when the supplied invention
does not support it.

Do not create artificial combinations merely to reach
the desired number of queries.

============================================================
INPUTS
============================================================

You will receive:

1. INNOVATION / INVENTION REPRESENTATION
2. KEYWORD ANALYSIS
3. CPC ANALYSIS

Use the invention representation to understand the
technical meaning.

Use KeywordAnalysis to identify terminology and synonyms.

Use CPCAnalysis to identify classification restrictions.

The generated queries should represent a sensible
professional search strategy based on all three inputs.

Return only structured query data.
"""

# ****************************************************************************************************************************************
# *                                                   Nodes definitions
# ****************************************************************************************************************************************


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


def generate_uspto_queries(
    state: PatentState,
    config: RunnableConfig,
) -> dict:
    configurable = config.get("configurable", {})
    context = configurable.get("context")
    thread_id = configurable.get("thread_id")
    if context is None:
        raise ValueError("Application context was not passed in runtime config.")

    llm = context.llm
    audit = context.audit
    if llm is None:
        raise ValueError("LLM instance is not available.")

    invention = state["invention"]
    keywords = state["keywords"]
    cpc_analysis = state["cpc_analysis"]
    # ---------------------------------------------------------
    # Build prompt
    # ---------------------------------------------------------
    prompt = f"""
    {USPTO_QUERY_SYSTEM_PROMPT}
    ========================
    INVENTION
    ========================
    {invention.model_dump_json(indent=2)}
    ========================
    KEYWORD ANALYSIS
    ========================
    {keywords.model_dump_json(indent=2)}
    ========================
    CPC ANALYSIS
    ========================
    {cpc_analysis.model_dump_json(indent=2)}

    Generate the USPTO search queries.
    """
    # ---------------------------------------------------------
    # Structured LLM output
    # ---------------------------------------------------------
    structured_llm = llm.with_structured_output(USPTOQueryAnalysis)
    result = structured_llm.invoke(prompt)

    # ---------------------------------------------------------
    # Audit
    # ---------------------------------------------------------

    function_name = inspect.currentframe().f_code.co_name

    audit.log_model_call(
        thread_id,
        function_name,
        prompt,
        result,
    )

    # ---------------------------------------------------------
    # Return state
    # ---------------------------------------------------------

    return {"uspto_queries": result}


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


def generate_espacenet_queries(
    state: PatentState,
    config: RunnableConfig,
) -> dict:
    configurable = config.get("configurable", {})
    context = configurable.get("context")
    thread_id = configurable.get("thread_id")
    print("ESP NODE: LLM IN")
    if context is None:
        raise ValueError("Application context was not passed in runtime config.")

    llm = context.llm
    audit = context.audit
    if llm is None:
        raise ValueError("LLM instance is not available.")

    invention = state["invention"]
    keywords = state["keywords"]
    cpc_analysis = state["cpc_analysis"]

    # ---------------------------------------------------------
    # Build prompt
    # ---------------------------------------------------------

    prompt = f"""
    {ESPACENET_QUERY_SYSTEM_PROMPT}
    ========================
    INVENTION
    ========================
    {invention.model_dump_json(indent=2)}
    ========================
    KEYWORD ANALYSIS
    ========================
    {keywords.model_dump_json(indent=2)}
    ========================
    CPC ANALYSIS
    ========================
    {cpc_analysis.model_dump_json(indent=2)}
    Generate the Espacenet search queries.
    """

    # ---------------------------------------------------------
    # Structured LLM output
    # ---------------------------------------------------------
    print("ESP NODE: LLM returned")
    structured_llm = llm.with_structured_output(EspacenetQueryAnalysis)
    # result = llm.invoke(prompt)
    result = structured_llm.invoke(prompt)
    print("ESP NODE: result returned")
    # ---------------------------------------------------------
    # Audit
    # ---------------------------------------------------------

    function_name = inspect.currentframe().f_code.co_name

    audit.log_model_call(
        thread_id,
        function_name,
        prompt,
        result,
    )

    # ---------------------------------------------------------
    # Return state
    # ---------------------------------------------------------

    return {"espacenet_queries": result}
