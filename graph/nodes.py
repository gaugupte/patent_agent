from __future__ import annotations

import inspect
import re
from typing import Any

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


# ****************************************************************************************************************************************
# *                                                   Prompts
# ****************************************************************************************************************************************


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
3. Never invent, reconstruct or alter a CPC title.
4. Evaluate candidates against the actual technical features
   of the invention, not merely keyword overlap.
5. Consider structural, procedural/process and functional
   aspects of the invention.
6. Do not require a CPC to cover the entire invention.
   A CPC covering an important technical aspect may be useful.
7. Retain secondary CPCs when they could reasonably improve
   the subsequent patent search.
8. Different invention features may legitimately map to
   different CPC classifications.
9. Do NOT select several classifications merely because they
   belong to the same CPC branch.
10. Avoid selecting multiple parent/child classifications
    when one sufficiently specific classification represents
    the same technical aspect.

RELEVANCE:

HIGH:
Directly covers an important technical aspect of the invention.

MEDIUM:
Covers an important component, function, process or technical
relationship, but is not the primary classification.

LOW:
Has a weaker but potentially useful technical relationship
and may be retained for broader searching.

IMPORTANT FEATURE-COVERAGE RULE:

Try to identify CPC classifications for DIFFERENT important
technical aspects of the invention.

For example, if the invention contains:
- a physical device,
- a liquid measurement mechanism,
- a temperature sensor,
- a motion/activity sensor,
- data processing,
- historical storage,
- communication,
- and adaptive recommendation logic,

do not allow one CPC family to dominate the result simply
because its embedding similarity is high.

Return approximately 5–15 strong CPC classifications when
justified.

For every selected CPC:
- provide the CPC code exactly as supplied
- identify the associated invention feature(s)
- assign HIGH, MEDIUM or LOW relevance
- explain the technical basis briefly

The CPC code and title supplied in the candidate list are
authoritative.
"""


USPTO_QUERY_SYSTEM_PROMPT = """
You are an experienced patent search strategist.

Your task is to generate a small set of high-quality search
queries for the USPTO Patent Public Search Advanced Search
interface.

The objective is to search for prior-art documents relating
to the INVENTION AS A WHOLE.

You are given:

1. Invention representation
2. Keyword analysis
3. Consolidated keywords
4. CPC analysis

============================================================
CORE SEARCH PRINCIPLE
============================================================

Do NOT make the primary search strategy:

feature → CPC → query

Instead, first construct searches representing the
overall technical combination of the invention.

Use:

SAME TECHNICAL CONCEPT → OR

DIFFERENT TECHNICAL CONCEPTS → AND

Do not put synonyms of the same concept together with AND.

============================================================
TEXT AND CPC ARE ALTERNATIVE SEARCH PATHS
============================================================

For broad searches, do NOT automatically require both
text terminology AND CPC classification.

CPC and text provide two different ways of finding
relevant prior art.

Therefore generate separate searches such as:

TEXT-BASED SEARCH:

("liquid level sensor"
 OR "fluid level sensor")
AND
("fluid intake"
 OR hydration)

CPC-BASED SEARCH:

(G01F23/00.CPC. OR G01F23/02.CPC.)

These are alternative retrieval paths.

============================================================
REQUIRED SEARCH STRATEGY
============================================================

Generate approximately 5–7 queries.

QUERY 1 — BROAD CONSOLIDATED TEXT SEARCH

QUERY 2 — ALTERNATIVE TEXT SEARCH

QUERY 3 — CPC SEARCH

QUERY 4 — CPC + CORE TEXT REFINEMENT

QUERY 5 — FEATURE-SPECIFIC SEARCH

QUERY 6 — CLAIMS-FOCUSED SEARCH

QUERY 7 — PROXIMITY REFINEMENT

Only generate Query 7 if proximity provides useful
additional search value.

============================================================
USPTO SYNTAX
============================================================

Boolean:

AND
OR
NOT

CPC:

G01F23/00.CPC.

Claims:

term.CLM.

Proximity:

term1 NEAR3 term2

Use parentheses for logical grouping.

============================================================
IMPORTANT RULES
============================================================

- Search the invention as a whole for the primary searches.
- Use consolidated_keywords as the main source for broad
  text searches.
- Use KeywordAnalysis to understand synonyms and alternative
  terminology.
- Use CPCAnalysis to identify CPC candidates.
- CPC codes must come ONLY from CPCAnalysis.
- Do not invent CPC classifications.
- Do not force CPC AND text for broad searches.
- Use OR between alternative CPC classifications.
- Use OR between synonyms.
- Use AND between distinct technical concepts.
- Do not create unnecessarily long queries.
- Do not use every available keyword.
- Prefer recall for the primary searches.
- Use narrower searches as secondary refinements.

Return only the structured output.
"""


ESPACENET_QUERY_SYSTEM_PROMPT = """
You are an experienced patent search strategist.

Your task is to generate a small set of high-quality search
queries for the EPO Espacenet Smart Search interface.

The objective is to search for prior-art documents relating
to the INVENTION AS A WHOLE.

You are given:

1. Invention representation
2. Keyword analysis
3. Consolidated keywords
4. CPC analysis

============================================================
CORE SEARCH PRINCIPLE
============================================================

Do NOT make the primary search strategy:

feature → CPC → query

Instead, first construct searches representing the
overall technical combination of the invention.

Use:

SAME TECHNICAL CONCEPT → OR

DIFFERENT TECHNICAL CONCEPTS → AND

============================================================
TEXT AND CPC ARE ALTERNATIVE SEARCH PATHS
============================================================

For broad searches, do NOT automatically require both
text terminology AND CPC classification.

CPC and text provide two different retrieval paths.

Generate separate searches such as:

TEXT SEARCH:

ftxt=("liquid level sensor"
      OR "fluid level sensor")
AND
ftxt=("fluid intake"
      OR hydration)

CPC SEARCH:

cpc=(G01F23/00 OR G01F23/02)

============================================================
REQUIRED SEARCH STRATEGY
============================================================

Generate approximately 5–7 queries.

QUERY 1 — BROAD CONSOLIDATED FULL-TEXT SEARCH

QUERY 2 — ALTERNATIVE FULL-TEXT SEARCH

QUERY 3 — CPC SEARCH

QUERY 4 — CPC + FULL-TEXT REFINEMENT

QUERY 5 — CPC HIERARCHY SEARCH

QUERY 6 — CLAIMS-FOCUSED SEARCH

QUERY 7 — PROXIMITY REFINEMENT

Only generate Query 7 if proximity provides meaningful
additional search value.

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

CPC hierarchy:

cpc=G01F23/00/low

Boolean:

AND
OR
NOT

Use parentheses for logical grouping.

============================================================
IMPORTANT RULES
============================================================

- Search the invention as a whole for the primary searches.
- Use consolidated_keywords as the main source for broad
  text searches.
- Use KeywordAnalysis to understand synonyms and alternative
  terminology.
- Use CPCAnalysis to identify CPC candidates.
- CPC codes must come ONLY from CPCAnalysis.
- Do not invent CPC classifications.
- Do not force CPC AND text for broad searches.
- Use OR between alternative CPC classifications.
- Use OR between synonyms.
- Use AND between distinct technical concepts.
- Do not create unnecessarily long queries.
- Do not use every available keyword.
- Prefer recall for the primary searches.
- Use narrower searches as secondary refinements.

Return only the structured output.
"""


# ****************************************************************************************************************************************
# *                                                   General helpers
# ****************************************************************************************************************************************


_GENERIC_TERMS = {
    "system",
    "device",
    "apparatus",
    "method",
    "process",
    "component",
    "module",
    "unit",
    "arrangement",
    "means",
    "data",
    "information",
    "technology",
    "technical",
    "operation",
    "operations",
    "processing",
    "processor",
    "sensor",
    "sensors",
    "monitor",
    "monitoring",
    "measurement",
    "measuring",
    "control",
    "controlling",
    "detector",
    "detecting",
    "detection",
    "structure",
    "element",
    "function",
    "functions",
}


_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "the",
    "their",
    "this",
    "that",
    "to",
    "with",
    "via",
    "using",
    "used",
    "use",
}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value).lower()

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _tokenize(
    value: Any,
    remove_generic: bool = False,
) -> set[str]:

    normalized = _normalize_text(value)

    tokens = {token for token in normalized.split() if token not in _STOP_WORDS and len(token) > 2}

    if remove_generic:
        tokens -= _GENERIC_TERMS

    return tokens


def _safe_join(
    values: list[Any],
) -> str:

    return " ".join(str(value).strip() for value in values if value is not None and str(value).strip())


def _feature_text(
    feature: Any,
) -> str:

    parts = []

    if hasattr(feature, "feature"):
        parts.append(feature.feature)

    if hasattr(feature, "step"):
        parts.append(feature.step)

    if hasattr(feature, "function"):
        parts.append(feature.function)

    if hasattr(feature, "details"):
        parts.append(feature.details)

    return _safe_join(parts)


def _keyword_text(
    item: Any,
) -> str:

    return _safe_join(
        [
            getattr(
                item,
                "feature",
                "",
            ),
            *getattr(
                item,
                "primary_keywords",
                [],
            ),
            *getattr(
                item,
                "synonyms",
                [],
            ),
            *getattr(
                item,
                "alternative_terms",
                [],
            ),
        ]
    )


# ****************************************************************************************************************************************
# *                                                   CPC retrieval helpers
# ****************************************************************************************************************************************


def _build_feature_retrieval_queries(
    invention: InventionRepresentation,
    keywords: KeywordAnalysis,
) -> list[dict[str, Any]]:
    """
    Build feature-balanced CPC retrieval queries.

    Every meaningful invention feature gets its own query,
    but each query is enriched with the overall invention
    context.

    This is intentionally different from the previous approach:
    the feature is NOT searched in isolation.
    """

    queries: list[dict[str, Any]] = []

    keyword_maps = {
        "structural": {item.feature_id: item for item in keywords.structural_keywords},
        "procedural": {item.feature_id: item for item in keywords.procedural_keywords},
        "functional": {item.feature_id: item for item in keywords.functional_keywords},
    }

    feature_groups = [
        (
            "structural",
            invention.structural_features,
        ),
        (
            "procedural",
            invention.procedural_features,
        ),
        (
            "functional",
            invention.functional_features,
        ),
    ]

    for category, features in feature_groups:
        for feature in features:
            keyword_item = keyword_maps[category].get(feature.feature_id)

            keyword_text = ""

            if keyword_item is not None:
                keyword_text = _keyword_text(keyword_item)

            query = _safe_join(
                [
                    invention.invention_summary,
                    _feature_text(feature),
                    keyword_text,
                ]
            )

            if not query:
                continue

            queries.append(
                {
                    "query_id": feature.feature_id,
                    "feature_id": feature.feature_id,
                    "category": category,
                    "query": query,
                }
            )

    return queries


def _build_category_queries(
    invention: InventionRepresentation,
    keywords: KeywordAnalysis,
) -> list[dict[str, Any]]:
    """
    Add a small number of category-level queries.

    These provide broader discovery without replacing the
    feature-balanced searches.
    """

    queries = []

    category_data = [
        (
            "Q_STRUCTURAL",
            "structural",
            keywords.structural_keywords,
        ),
        (
            "Q_PROCEDURAL",
            "procedural",
            keywords.procedural_keywords,
        ),
        (
            "Q_FUNCTIONAL",
            "functional",
            keywords.functional_keywords,
        ),
    ]

    for query_id, category, items in category_data:
        query = _safe_join(
            [
                invention.invention_summary,
                *[_keyword_text(item) for item in items],
            ]
        )

        if not query:
            continue

        queries.append(
            {
                "query_id": query_id,
                "feature_id": None,
                "category": category,
                "query": query,
            }
        )

    return queries


def _build_feature_sets(
    invention: InventionRepresentation,
    keywords: KeywordAnalysis,
) -> list[dict[str, Any]]:

    feature_sets = []

    keyword_maps = {
        "structural": {item.feature_id: item for item in keywords.structural_keywords},
        "procedural": {item.feature_id: item for item in keywords.procedural_keywords},
        "functional": {item.feature_id: item for item in keywords.functional_keywords},
    }

    groups = [
        (
            "structural",
            invention.structural_features,
        ),
        (
            "procedural",
            invention.procedural_features,
        ),
        (
            "functional",
            invention.functional_features,
        ),
    ]

    for category, features in groups:
        for feature in features:
            keyword_item = keyword_maps[category].get(feature.feature_id)

            primary = []
            synonyms = []
            alternatives = []

            if keyword_item is not None:
                primary = list(
                    getattr(
                        keyword_item,
                        "primary_keywords",
                        [],
                    )
                )

                synonyms = list(
                    getattr(
                        keyword_item,
                        "synonyms",
                        [],
                    )
                )

                alternatives = list(
                    getattr(
                        keyword_item,
                        "alternative_terms",
                        [],
                    )
                )

            feature_text = _feature_text(feature)

            feature_sets.append(
                {
                    "feature_id": feature.feature_id,
                    "category": category,
                    "feature_text": feature_text,
                    "primary": primary,
                    "synonyms": synonyms,
                    "alternatives": alternatives,
                    "feature_tokens": _tokenize(
                        feature_text,
                        remove_generic=True,
                    ),
                    "primary_tokens": _tokenize(
                        " ".join(primary),
                        remove_generic=True,
                    ),
                    "synonym_tokens": _tokenize(
                        " ".join(synonyms),
                        remove_generic=True,
                    ),
                    "alternative_tokens": _tokenize(
                        " ".join(alternatives),
                        remove_generic=True,
                    ),
                }
            )

    return feature_sets


def _candidate_text(
    candidate: dict[str, Any],
) -> str:

    return _safe_join(
        [
            candidate.get(
                "title",
                "",
            ),
            candidate.get(
                "parent_title",
                "",
            ),
            candidate.get(
                "hierarchy_titles",
                "",
            ),
        ]
    )


def _phrase_match(
    candidate_text: str,
    phrases: list[str],
) -> int:

    normalized_candidate = _normalize_text(candidate_text)

    count = 0

    for phrase in phrases:
        normalized_phrase = _normalize_text(phrase)

        if normalized_phrase and normalized_phrase in normalized_candidate:
            count += 1

    return count


def _keyword_score(
    candidate_text: str,
    feature_sets: list[dict[str, Any]],
) -> tuple[float, list[str]]:

    candidate_tokens = _tokenize(
        candidate_text,
        remove_generic=True,
    )

    if not candidate_tokens:
        return 0.0, []

    weighted_total = 0.0
    weighted_match = 0.0

    matched_terms = []

    for feature in feature_sets:
        for token in feature["primary_tokens"]:
            weighted_total += 3.0

            if token in candidate_tokens:
                weighted_match += 3.0
                matched_terms.append(token)

        for token in feature["synonym_tokens"]:
            weighted_total += 2.0

            if token in candidate_tokens:
                weighted_match += 2.0
                matched_terms.append(token)

        for token in feature["alternative_tokens"]:
            weighted_total += 1.0

            if token in candidate_tokens:
                weighted_match += 1.0
                matched_terms.append(token)

        phrases = feature["primary"] + feature["synonyms"] + feature["alternatives"]

        phrase_matches = _phrase_match(
            candidate_text,
            phrases,
        )

        if phrase_matches:
            weighted_total += 4.0
            weighted_match += min(
                4.0,
                phrase_matches * 2.0,
            )

    if weighted_total <= 0:
        return 0.0, []

    score = min(
        1.0,
        weighted_match / weighted_total,
    )

    return (
        score,
        sorted(set(matched_terms)),
    )


def _feature_scores(
    candidate_text: str,
    feature_sets: list[dict[str, Any]],
) -> dict[str, float]:

    candidate_tokens = _tokenize(
        candidate_text,
        remove_generic=True,
    )

    scores = {}

    for feature in feature_sets:
        evidence = feature["feature_tokens"] | feature["primary_tokens"] | feature["synonym_tokens"] | feature["alternative_tokens"]

        if not evidence:
            scores[feature["feature_id"]] = 0.0

            continue

        overlap = candidate_tokens & evidence

        # Stronger score when multiple technical concepts
        # belonging to the feature are present.
        scores[feature["feature_id"]] = min(
            1.0,
            len(overlap) / 4.0,
        )

    return scores


def _semantic_rank_score(
    rank: int,
    result_count: int,
) -> float:
    """
    We use rank rather than interpreting Chroma's numeric
    distance as cosine similarity.

    Lower Chroma distance means better retrieval, but the
    exact distance metric should not be assumed here.
    """

    if result_count <= 1:
        return 1.0

    return max(
        0.0,
        1.0 - (rank / result_count),
    )


def _rerank_candidates(
    candidates: dict[str, dict[str, Any]],
    feature_sets: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    ranked = []

    for candidate in candidates.values():
        text = _candidate_text(candidate)

        keyword_score, matched_terms = _keyword_score(
            text,
            feature_sets,
        )

        feature_scores = _feature_scores(
            text,
            feature_sets,
        )

        covered_features = [feature_id for feature_id, score in feature_scores.items() if score >= 0.25]

        if feature_scores:
            feature_coverage = sum(feature_scores.values()) / len(feature_scores)

        else:
            feature_coverage = 0.0

        # A candidate retrieved by several distinct feature
        # queries is stronger than one retrieved only once.
        query_diversity = min(
            1.0,
            len(
                candidate.get(
                    "query_ids",
                    [],
                )
            )
            / 4.0,
        )

        semantic_score = candidate.get(
            "semantic_score",
            0.0,
        )

        final_score = 0.45 * semantic_score + 0.25 * keyword_score + 0.20 * feature_coverage + 0.10 * query_diversity

        candidate["keyword_score"] = round(
            keyword_score,
            4,
        )

        candidate["feature_coverage"] = round(
            feature_coverage,
            4,
        )

        candidate["query_diversity"] = round(
            query_diversity,
            4,
        )

        candidate["retrieval_score"] = round(
            final_score,
            4,
        )

        candidate["matched_terms"] = matched_terms

        candidate["covered_features"] = covered_features

        candidate["feature_scores"] = feature_scores

        ranked.append(candidate)

    ranked.sort(
        key=lambda item: (
            item["retrieval_score"],
            item.get(
                "retrieval_hits",
                0,
            ),
        ),
        reverse=True,
    )

    return ranked


def _select_diverse_candidates(
    ranked_candidates: list[dict[str, Any]],
    feature_sets: list[dict[str, Any]],
    max_candidates: int,
) -> list[dict[str, Any]]:
    """
    Feature-balanced final candidate selection.

    First reserve one candidate for each feature where a
    meaningful candidate exists.

    Then fill remaining slots globally by retrieval score.

    This is the important protection against the previous
    failure mode where one CPC family consumed the entire
    LLM candidate pool.
    """

    selected: list[dict[str, Any]] = []

    selected_codes = set()

    # ---------------------------------------------------------
    # Pass 1:
    # one best candidate per feature
    # ---------------------------------------------------------

    for feature in feature_sets:
        feature_id = feature["feature_id"]

        best = None
        best_feature_score = 0.0

        for candidate in ranked_candidates:
            code = candidate["cpc_code"]

            if code in selected_codes:
                continue

            feature_score = candidate["feature_scores"].get(
                feature_id,
                0.0,
            )

            if feature_score > best_feature_score:
                best = candidate
                best_feature_score = feature_score

        if best is not None and best_feature_score >= 0.25:
            selected.append(best)

            selected_codes.add(best["cpc_code"])

            if len(selected) >= max_candidates:
                return selected

    # ---------------------------------------------------------
    # Pass 2:
    # global best candidates
    # ---------------------------------------------------------

    for candidate in ranked_candidates:
        if candidate["cpc_code"] in selected_codes:
            continue

        selected.append(candidate)

        selected_codes.add(candidate["cpc_code"])

        if len(selected) >= max_candidates:
            break

    return selected


def _extract_candidate_codes(
    candidates: list[dict[str, Any]],
) -> set[str]:

    return {str(candidate.get("cpc_code", "")).strip() for candidate in candidates if candidate.get("cpc_code")}


def _restore_authoritative_cpc_data(
    result: CPCAnalysis,
    candidate_map: dict[str, dict[str, Any]],
) -> CPCAnalysis:
    """
    The LLM decides relevance, but the corpus remains authoritative
    for CPC identity/title.

    Any CPC not present in the retrieved candidate map is removed.

    Titles are restored from the CPC corpus after LLM evaluation.
    """

    if not hasattr(
        result,
        "candidates",
    ):
        return result

    valid_candidates = []

    for selected in result.candidates:
        cpc_code = str(
            getattr(
                selected,
                "cpc_code",
                "",
            )
        ).strip()

        if not cpc_code:
            continue

        source = candidate_map.get(cpc_code)

        if source is None:
            print(f"CPC WARNING: LLM returned CPC not in candidate pool: {cpc_code}")
            continue

        # -----------------------------------------------------
        # Never trust an LLM-generated title.
        # -----------------------------------------------------

        authoritative_title = source.get(
            "title",
            "",
        )

        if hasattr(
            selected,
            "title",
        ):
            try:
                selected.title = authoritative_title
            except Exception:
                pass

        # -----------------------------------------------------
        # If feature_id is empty, use retrieval evidence.
        # -----------------------------------------------------

        existing_feature_id = getattr(
            selected,
            "feature_id",
            None,
        )

        if not existing_feature_id:
            covered = source.get(
                "covered_features",
                [],
            )

            if covered:
                try:
                    selected.feature_id = covered[0]
                except Exception:
                    pass

        valid_candidates.append(selected)

    result.candidates = valid_candidates

    return result


# ****************************************************************************************************************************************
# *                                                   Nodes
# ****************************************************************************************************************************************


def decompose_invention(
    state: PatentState,
    config: RunnableConfig,
) -> dict:

    idf_text = state["idf_text"]

    configurable = config.get(
        "configurable",
        {},
    )

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

    audit.log_model_call(
        thread_id,
        function_name,
        state["idf_text"],
        result,
    )

    print("decompose_invention")

    return {"invention": result}


def create_invention_pdf(
    state: PatentState,
    config: RunnableConfig,
):

    configurable = config.get(
        "configurable",
        {},
    )

    context = configurable.get("context")

    pdf_path = context.pdf_service.create_invention_pdf(
        session_id=state["session_id"],
        invention=state["invention"],
    )

    print("create_invention_pdf")

    return {"pdf_path": pdf_path}


def generate_keywords(
    state: PatentState,
    config: RunnableConfig,
) -> dict:

    configurable = config.get(
        "configurable",
        {},
    )

    context = configurable.get("context")

    thread_id = configurable.get("thread_id")

    audit = context.audit
    llm = context.llm

    if not llm:
        raise ValueError("LLM instance was not passed in the runtime config.")

    invention = state["invention"]

    structured_llm = llm.with_structured_output(KeywordAnalysis)

    # IMPORTANT:
    # The old implementation incorrectly used DECOMPOSE_PROMPT.
    # Keyword generation must use KEYWORDS_PROMPT.
    prompt = f"""
{KEYWORDS_PROMPT}

Here is the structured representation of the invention.

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

    audit.log_model_call(
        thread_id,
        function_name,
        prompt,
        result,
    )

    print("KEYWORDS NODE")

    return {"keywords": result}


# ****************************************************************************************************************************************
# *                                                   CPC LOOKUP V3
# ****************************************************************************************************************************************


def lookup_cpc(
    state: PatentState,
    config: RunnableConfig,
) -> dict:

    print("Inside lookup_cpc ****************")

    configurable = config.get("configurable", {})

    context = configurable.get("context")

    thread_id = configurable.get("thread_id")

    if context is None:
        raise ValueError("Application context was not passed in runtime config.")

    llm = context.llm
    audit = context.audit
    cpc_vector_store = context.vector_store

    print("CPC VECTOR STORE:", type(cpc_vector_store))

    print("CPC COLLECTION:", getattr(cpc_vector_store, "_collection", None))

    print("CPC COUNT:", cpc_vector_store._collection.count())

    if llm is None:
        raise ValueError("LLM instance is not available.")

    if cpc_vector_store is None:
        raise ValueError("CPC vector store is not available.")

    invention = state["invention"]
    keyword_analysis = state["keywords"]

    # =========================================================
    # CONFIGURATION
    # =========================================================

    FEATURE_TOP_K = 10
    CATEGORY_TOP_K = 12
    MAX_RAW_CANDIDATES = 100
    MAX_CANDIDATES_PER_EVALUATION = 8

    # =========================================================
    # 1. Build feature queries
    # =========================================================

    feature_queries = []
    keyword_maps = {
        "structural": {item.feature_id: item for item in keyword_analysis.structural_keywords},
        "procedural": {item.feature_id: item for item in keyword_analysis.procedural_keywords},
        "functional": {item.feature_id: item for item in keyword_analysis.functional_keywords},
    }

    feature_groups = [
        ("structural", invention.structural_features),
        ("procedural", invention.procedural_features),
        ("functional", invention.functional_features),
    ]

    for category, features in feature_groups:
        for feature in features:
            keyword_item = keyword_maps[category].get(feature.feature_id)
            keyword_text = ""
            if keyword_item is not None:
                keyword_text = " ".join(
                    [
                        *keyword_item.primary_keywords,
                        *keyword_item.synonyms,
                        *keyword_item.alternative_terms,
                    ]
                )

            feature_text = " ".join([_feature_text(feature)]).strip()
            # feature_text = " ".join([invention.invention_summary, _feature_text(feature), keyword_text]).strip()

            if not feature_text:
                continue

            feature_queries.append(
                {
                    "feature_id": feature.feature_id,
                    "category": category,
                    "feature_text": _feature_text(feature),
                    "query": feature_text,
                }
            )

    print("==================================================")
    print("CPC RETRIEVAL")
    print("Feature queries:", len(feature_queries))

    # =========================================================
    # 2. Retrieve candidates
    # =========================================================

    candidates = {}

    for query_item in feature_queries:
        # print("------------------Look here--------------------------------")
        # print("FEATURE ID:", query_item["feature_id"])
        # print("CATEGORY:", query_item["category"])
        # print("FEATURE TEXT:", query_item["feature_text"])
        # print("FULL RETRIEVAL QUERY:", query_item["query"])
        documents = cpc_vector_store.similarity_search_with_score(
            query_item["query"],
            k=FEATURE_TOP_K,
        )

        print(f"CPC RETRIEVAL: {query_item['feature_id']} -> {len(documents)} results")

        for rank, (doc, score) in enumerate(
            documents,
            start=1,
        ):
            metadata = (
                getattr(
                    doc,
                    "metadata",
                    {},
                )
                or {}
            )

            # =================================================
            # IMPORTANT
            #
            # CPC ingestion stores the CPC classification
            # code under metadata["code"], not
            # metadata["cpc_code"].
            # =================================================

            cpc_code = metadata.get("code")

            if not cpc_code:
                continue

            cpc_code = str(cpc_code).strip()

            if not cpc_code:
                continue

            title = metadata.get("title") or getattr(
                doc,
                "page_content",
                "",
            )

            hierarchy_titles = metadata.get(
                "hierarchy_titles",
                "",
            )

            parent_title = metadata.get(
                "parent_title",
                "",
            )

            if cpc_code not in candidates:
                candidates[cpc_code] = {
                    "cpc_code": cpc_code,
                    "title": str(title),
                    "hierarchy_titles": str(hierarchy_titles),
                    "parent_title": str(parent_title),
                    "best_distance": float(score),
                    "retrieval_hits": 1,
                    "feature_ids": [query_item["feature_id"]],
                    "categories": [query_item["category"]],
                }

            else:
                candidate = candidates[cpc_code]

                candidate["retrieval_hits"] += 1

                feature_id = query_item["feature_id"]

                if feature_id not in candidate["feature_ids"]:
                    candidate["feature_ids"].append(feature_id)

                category = query_item["category"]

                if category not in candidate["categories"]:
                    candidate["categories"].append(category)

                if float(score) < candidate["best_distance"]:
                    candidate["best_distance"] = float(score)

    print("Raw CPC candidates:", len(candidates))

    if not candidates:
        raise RuntimeError("CPC retrieval returned zero candidates. The CPC vector store or retrieval configuration must be investigated before continuing.")

    # =========================================================
    # 3. Bound raw candidate pool
    # =========================================================

    ranked_candidates = sorted(
        candidates.values(),
        key=lambda item: (item["retrieval_hits"], -item["best_distance"]),
        reverse=True,
    )

    ranked_candidates = ranked_candidates[:MAX_RAW_CANDIDATES]

    # =========================================================
    # 4. Build candidate lookup
    # =========================================================

    candidate_map = {candidate["cpc_code"]: candidate for candidate in ranked_candidates}

    # =========================================================
    # 5. Evaluate CPCs by technical feature
    # =========================================================

    all_selected = {}

    # Evaluate every important feature separately.
    # This prevents one CPC family from dominating
    # the entire result.

    for query_item in feature_queries:
        feature_id = query_item["feature_id"]

        feature_candidates = [
            candidate
            for candidate in ranked_candidates
            if feature_id
            in candidate.get(
                "feature_ids",
                [],
            )
        ]

        if not feature_candidates:
            print(f"CPC: no candidates for {feature_id}")

            continue

        feature_candidates = sorted(
            feature_candidates,
            key=lambda item: (
                item["retrieval_hits"],
                -item["best_distance"],
            ),
            reverse=True,
        )

        feature_candidates = feature_candidates[:MAX_CANDIDATES_PER_EVALUATION]

        candidate_blocks = []

        for index, candidate in enumerate(
            feature_candidates,
            start=1,
        ):
            candidate_blocks.append(
                f"""
CANDIDATE {index}

CPC CODE:
{candidate["cpc_code"]}

AUTHORITATIVE TITLE:
{candidate["title"]}

PARENT:
{candidate["parent_title"]}

HIERARCHY:
{candidate["hierarchy_titles"]}

RETRIEVAL HITS:
{candidate["retrieval_hits"]}
"""
            )

        candidate_text = "\n".join(candidate_blocks)

        prompt = f"""
You are a patent classification specialist.

Identify CPC classifications that are technically relevant
to the INVENTION FEATURE described below.

IMPORTANT:

- Select CPC codes ONLY from the supplied candidates.
- Never invent a CPC code.
- Never modify a CPC code.
- Do not invent a CPC title.
- The supplied title is authoritative.
- Reject classifications belonging to unrelated technical
  domains.
- Generic words such as "sensor", "processor", "system",
  "device", "measurement", or "data" are NOT sufficient
  evidence of relevance.

A CPC may be selected even if it covers only this particular
feature rather than the complete invention.

Evaluate the FEATURE on its own technical merits, while
considering the overall invention context.

============================================================
OVERALL INVENTION
============================================================

{invention.invention_summary}

============================================================
FEATURE ID
============================================================

{feature_id}

============================================================
FEATURE
============================================================

{query_item["feature_text"]}

============================================================
FEATURE KEYWORDS
============================================================

{query_item["query"]}

============================================================
CANDIDATE CPC CLASSIFICATIONS
============================================================

{candidate_text}

============================================================
INSTRUCTIONS
============================================================

Select the CPC classifications that genuinely correspond
to this feature.

Prefer the most technically specific useful CPC.

Do not select multiple parent/child classifications merely
because they belong to the same hierarchy.

Normally select 0–3 CPC classifications for this feature.

If none is genuinely relevant, return an empty list.

For each selected CPC provide:

- cpc_code
- feature_id
- relevance
- reason

The cpc_code MUST exactly match one of the candidates above.
"""

        structured_llm = llm.with_structured_output(CPCAnalysis)

        print(f"CPC: evaluating {feature_id}")

        result = structured_llm.invoke(prompt)

        print(f"CPC: {feature_id} returned {len(result.candidates)} candidates")

        # =====================================================
        # 6. Validate each LLM selection
        # =====================================================

        for selected in result.candidates:
            cpc_code = str(
                getattr(
                    selected,
                    "cpc_code",
                    "",
                )
            ).strip()

            if not cpc_code:
                print(f"CPC WARNING: empty CPC code returned for {feature_id}")

                continue

            source_candidate = candidate_map.get(cpc_code)

            if source_candidate is None:
                print(f"CPC WARNING: LLM returned CPC {cpc_code}, but it was not in the retrieved candidate pool.")

                continue

            # -------------------------------------------------
            # Store authoritative corpus information.
            # -------------------------------------------------

            if cpc_code not in all_selected:
                all_selected[cpc_code] = {
                    "selected": selected,
                    "source": source_candidate,
                    "feature_ids": [feature_id],
                }

            else:
                if feature_id not in all_selected[cpc_code]["feature_ids"]:
                    all_selected[cpc_code]["feature_ids"].append(feature_id)

    # =========================================================
    # 7. IMPORTANT: don't silently return blank CPC analysis
    # =========================================================

    print("==================================================")

    print("CPC SELECTION")

    print(
        "Unique CPCs selected:",
        len(all_selected),
    )

    if not all_selected:
        raise RuntimeError("CPC evaluation returned zero valid CPC classifications after validation. The pipeline has therefore stopped instead of generating a misleading blank CPC report.")

    # =========================================================
    # 8. Reconstruct final CPCAnalysis
    # =========================================================

    final_candidates = []

    for cpc_code, data in all_selected.items():
        selected = data["selected"]

        source = data["source"]

        # -----------------------------------------------------
        # Restore authoritative title.
        # -----------------------------------------------------

        if hasattr(
            selected,
            "title",
        ):
            selected.title = source["title"]

        # -----------------------------------------------------
        # Preserve feature association.
        # -----------------------------------------------------

        feature_ids = data["feature_ids"]

        if feature_ids and hasattr(
            selected,
            "feature_id",
        ):
            selected.feature_id = feature_ids[0]

        final_candidates.append(selected)

    # =========================================================
    # 9. Construct final CPCAnalysis
    # =========================================================

    final_result = CPCAnalysis(candidates=final_candidates)

    # =========================================================
    # 10. Audit each evaluation
    # =========================================================

    function_name = inspect.currentframe().f_code.co_name

    audit.log_model_call(
        thread_id,
        function_name,
        (f"CPC feature-level evaluation. Features evaluated: {len(feature_queries)}. Final CPCs: {len(final_candidates)}."),
        final_result,
    )

    print("==================================================")

    print("FINAL CPC ANALYSIS")

    for candidate in final_candidates:
        print(f"{candidate.cpc_code} | {candidate.title} | {candidate.feature_id} | {candidate.relevance}")

    print("lookup_cpc")

    return {"cpc_analysis": final_result}


# ****************************************************************************************************************************************
# *                                                   USPTO queries
# ****************************************************************************************************************************************


def generate_uspto_queries(
    state: PatentState,
    config: RunnableConfig,
) -> dict:

    configurable = config.get(
        "configurable",
        {},
    )

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

    prompt = f"""
{USPTO_QUERY_SYSTEM_PROMPT}

========================
INVENTION
========================

{invention.model_dump_json(indent=2)}

========================
CONSOLIDATED KEYWORDS
========================

{keywords.consolidated_keywords}

========================
FULL KEYWORD ANALYSIS
========================

{keywords.model_dump_json(indent=2)}

========================
CPC ANALYSIS
========================

{cpc_analysis.model_dump_json(indent=2)}

Generate the USPTO search queries.
"""

    structured_llm = llm.with_structured_output(USPTOQueryAnalysis)

    print("USPTO: before invoke")

    result = structured_llm.invoke(prompt)

    print("USPTO: after invoke")

    print(result)

    function_name = inspect.currentframe().f_code.co_name

    audit.log_model_call(
        thread_id,
        function_name,
        prompt,
        result,
    )

    print("uspto")

    return {"uspto_queries": result}


# ****************************************************************************************************************************************
# *                                                   Espacenet queries
# ****************************************************************************************************************************************


def generate_espacenet_queries(
    state: PatentState,
    config: RunnableConfig,
) -> dict:

    configurable = config.get(
        "configurable",
        {},
    )

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

    prompt = f"""
{ESPACENET_QUERY_SYSTEM_PROMPT}

========================
INVENTION
========================

{invention.model_dump_json(indent=2)}

========================
CONSOLIDATED KEYWORDS
========================

{keywords.consolidated_keywords}

========================
FULL KEYWORD ANALYSIS
========================

{keywords.model_dump_json(indent=2)}

========================
CPC ANALYSIS
========================

{cpc_analysis.model_dump_json(indent=2)}

Generate the Espacenet search queries.
"""

    structured_llm = llm.with_structured_output(EspacenetQueryAnalysis)

    print("ESPACENET: before invoke")

    result = structured_llm.invoke(prompt)

    print("ESPACENET: after invoke")

    print(result)

    function_name = inspect.currentframe().f_code.co_name

    audit.log_model_call(
        thread_id,
        function_name,
        prompt,
        result,
    )

    print("espacenet")

    return {"espacenet_queries": result}


# ****************************************************************************************************************************************
# *                                                   Client report
# ****************************************************************************************************************************************


def create_client_report(
    state: PatentState,
    config: RunnableConfig,
) -> dict:

    configurable = config.get(
        "configurable",
        {},
    )

    context = configurable.get("context")

    thread_id = configurable.get("thread_id")

    if context is None:
        raise ValueError("Application context was not passed in runtime config.")

    report_path = context.report_service.create_client_report(
        state=state,
        session_id=thread_id,
    )

    print("client_report")

    return {"report_path": report_path}
