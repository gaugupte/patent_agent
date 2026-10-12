from __future__ import annotations

import inspect
import re
from typing import Any
from unittest import result

from config.state import PatentState

from models.patent_models import (
    InventionRepresentation,
    KeywordAnalysis,
    CPCAnalysis,
    USPTOQuery,
    USPTOQueryAnalysis,
    EspacenetQuery,
    EspacenetQueryAnalysis,
)

from langchain_core.runnables import RunnableConfig

from config.config import ApplicationContext, Settings

import torch
from sentence_transformers import SentenceTransformer, CrossEncoder
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

Your task is to generate USPTO Patent Public Search Advanced
Search queries for the invention.

You are given two independent sources:

1. KEYWORD ANALYSIS
2. CPC ANALYSIS

The two sources MUST be used separately.

============================================================
REQUIRED OUTPUT
============================================================

Generate exactly FOUR types of USPTO queries:

1. TITLE
2. DESCRIPTION
3. CLAIMS
4. CPC

Do not generate any other query type.

============================================================
1. TITLE QUERIES
============================================================

Use the Keyword Analysis to identify the most important
technical concepts representing the invention.

Construct a small number of TITLE queries using:

.TI.

Same technical concept:
    OR

Different technical concepts:
    AND

Example:

("immersion cooling" OR "dielectric cooling")
AND
("battery pack" OR "battery cells").TI.

The query must represent the invention as a whole as far
as reasonably possible.

Do not use CPC codes in TITLE queries.

============================================================
2. DESCRIPTION QUERIES
============================================================

Use the Keyword Analysis to construct searches for the
description/specification.

Use:

.SPEC.

Same technical concept:
    OR

Different technical concepts:
    AND

Example:

("immersion cooling" OR "dielectric cooling")
AND
("battery cells" OR "battery pack")
AND
("thermoelectric cooling" OR Peltier).SPEC.

Do not use CPC codes in DESCRIPTION queries.

============================================================
3. CLAIMS QUERIES
============================================================

Use the Keyword Analysis to construct searches for claims.

Use:

.CLM.

Same technical concept:
    OR

Different technical concepts:
    AND

Example:

("immersion cooling" OR "dielectric cooling")
AND
("battery cells" OR "battery pack")
AND
(Peltier OR "thermoelectric cooling").CLM.

Do not use CPC codes in CLAIMS queries.

============================================================
4. CPC QUERIES
============================================================

Use ONLY the CPC codes supplied in CPC ANALYSIS.

Do not generate, modify, infer or invent CPC codes.

CPC searches MUST use:

.CPC.

Use OR between alternative CPC classifications.

Example:

(H01M50/00.CPC.
 OR B60L58/24.CPC.
 OR F28D9/00.CPC.)

Do not use CPC titles as search terms.

Do not copy the CPC title or purpose into the query.

============================================================
KEYWORD COMBINATION RULES
============================================================

Use the terminology supplied in KEYWORD ANALYSIS.

For the SAME technical concept:

    OR

Example:

("immersion cooling"
 OR "dielectric cooling"
 OR "thermal cooling")

For DIFFERENT technical concepts:

    AND

Example:

("immersion cooling"
 OR "dielectric cooling")
AND
("battery cells"
 OR "battery pack")
AND
(Peltier OR "thermoelectric cooling")

Do not simply concatenate all available keywords.

Do not use every keyword.

Prefer the strongest technically meaningful terms.

Do not introduce technical concepts that are not present
in the supplied Keyword Analysis.

============================================================
USPTO SYNTAX
============================================================

TITLE:

(expression).TI.

DESCRIPTION:

(expression).SPEC.

CLAIMS:

(expression).CLM.

CPC:

(expression.CPC. OR expression.CPC.)

Boolean operators:

AND
OR
NOT

Use parentheses for logical grouping.

Every generated query must be directly executable by
copying it into USPTO Patent Public Search Advanced Search.

Do not generate natural-language explanations inside the
query field.

Do not generate Markdown.

Do not generate placeholders.

============================================================
QUERY COUNT
============================================================

Generate approximately:

TITLE:
1–2 queries

DESCRIPTION:
2–3 queries

CLAIMS:
1–2 queries

CPC:
1 query

Keep the total number of queries small and useful.

============================================================
IMPORTANT
============================================================

TITLE, DESCRIPTION and CLAIMS queries come from
KEYWORD ANALYSIS.

CPC queries come from CPC ANALYSIS.

Do not mix these responsibilities.

Return only the structured USPTOQueryAnalysis output.
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

    # print("decompose_invention:" + 40 * "=")
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
    audit.log_model_call(thread_id, function_name, prompt, result)
    # print("KEYWORDS NODE")
    return {"keywords": result}


# ****************************************************************************************************************************************
# *                                                   CPC LOOKUP V3
# ****************************************************************************************************************************************

# ============================================================
# CPC retrieval / reranking models
# ============================================================
_CPC_BI_ENCODER = None
_CPC_CROSS_ENCODER = None


def _get_cpc_retrieval_models():
    # ! this function should be part of bootstrapper?

    global _CPC_BI_ENCODER
    global _CPC_CROSS_ENCODER

    device = "cuda" if torch.cuda.is_available() else "cpu"

    if _CPC_BI_ENCODER is None:
        print(f"[CPC] Loading bi-encoder datalyes/patembed-large on {device.upper()}...")

        _CPC_BI_ENCODER = SentenceTransformer("datalyes/patembed-large", device=device)
        _CPC_BI_ENCODER.max_seq_length = 512
        _CPC_BI_ENCODER.tokenizer.model_max_length = 512

        if device == "cuda":
            _CPC_BI_ENCODER.half()

    if _CPC_CROSS_ENCODER is None:
        print(f"[CPC] Loading cross-encoder BAAI/bge-reranker-large on {device.upper()}...")
        _CPC_CROSS_ENCODER = CrossEncoder("BAAI/bge-reranker-large", device=device)

    return _CPC_BI_ENCODER, _CPC_CROSS_ENCODER


def lookup_cpc(state: PatentState, config: RunnableConfig) -> dict:

    print()
    print("=" * 90)
    print("INSIDE LOOKUP_CPC")
    print("=" * 90)

    configurable = config.get("configurable", {})
    context = configurable.get("context")
    thread_id = configurable.get("thread_id")

    if context is None:
        raise ValueError("Application context was not passed in runtime config.")
    if context.vector_store is None:
        raise ValueError("CPC vector store is not available.")

    invention = state["invention"]
    cpc_vector_store = context.vector_store
    # print("CPC VECTOR STORE:", type(cpc_vector_store))

    # ---------------------------------------------------------
    # Verify CPC collection
    # ---------------------------------------------------------

    try:
        collection_count = cpc_vector_store._collection.count()
    except Exception as exc:
        raise RuntimeError(f"Unable to access CPC Chroma collection: {exc}") from exc

    # print("CPC COUNT:", collection_count)

    if collection_count == 0:
        raise RuntimeError("CPC vector store contains zero records.")

    # 1. Build the three specialized queries
    # STRUCTURAL    # PROCEDURAL     # FUNCTIONAL

    structural_text = _safe_join([_feature_text(feature) for feature in invention.structural_features])
    procedural_text = _safe_join([_feature_text(feature) for feature in invention.procedural_features])
    functional_text = _safe_join([_feature_text(feature) for feature in invention.functional_features])
    queries = {
        "STRUCTURAL": ("Structural hardware components elements devices apparatus: " + structural_text),
        "PROCEDURAL": ("Procedural steps methods operations protocol algorithms: " + procedural_text),
        "FUNCTIONAL": ("Functional objective purpose utility use-case capability: " + functional_text),
    }

    # 2. Load the model
    bi_encoder, cross_encoder = _get_cpc_retrieval_models()

    # 3. Retrieve TOP 15 from EACH category

    RETRIEVAL_TOP_K = 15
    unique_candidates = {}

    for query_type, query_text in queries.items():
        if not query_text.strip():
            continue
        # -----------------------------------------------------
        # Generate query embedding
        # -----------------------------------------------------
        with torch.no_grad():
            query_vector = bi_encoder.encode(query_text, convert_to_numpy=True).tolist()

        # Query Chroma directly
        raw_results = cpc_vector_store._collection.query(query_embeddings=[query_vector], n_results=RETRIEVAL_TOP_K)
        if not raw_results:
            print("No results returned.")
            continue

        documents_matrix = raw_results.get("documents")
        metadatas_matrix = raw_results.get("metadatas")
        if not documents_matrix:
            print("No documents returned.")
            continue
        documents = documents_matrix[0]
        if metadatas_matrix:
            metadatas = metadatas_matrix[0]
        else:
            metadatas = [{} for _ in documents]
        # -----------------------------------------------------
        # Store candidates
        # -----------------------------------------------------
        # print()
        # print(f"TOP {RETRIEVAL_TOP_K} {query_type} CPC RESULTS")

        for rank, document in enumerate(documents, start=1):
            metadata = metadatas[rank - 1] if rank - 1 < len(metadatas) else {}

            if metadata is None:
                metadata = {}

            # Your current CPC database uses "code".
            # test_cpc_db.py uses "cpc_code".
            cpc_code = str(metadata.get("cpc_code", metadata.get("code", ""))).strip()
            title = str(metadata.get("title", "")).strip()

            if not cpc_code or not title:
                continue

            # print(f"{rank:2}. {cpc_code:<16} | {title}")

            # -------------------------------------------------
            # Deduplicate across the three retrieval passes.
            # -------------------------------------------------

            if cpc_code not in unique_candidates:
                unique_candidates[cpc_code] = {
                    "cpc_code": cpc_code,
                    "title": title,
                    "doc": document,
                    "metadata": metadata,
                    "retrieved_from": [query_type],
                    "retrieval_ranks": {query_type: rank},
                }

            else:
                candidate = unique_candidates[cpc_code]
                if query_type not in candidate["retrieved_from"]:
                    candidate["retrieved_from"].append(query_type)
                candidate["retrieval_ranks"][query_type] = rank
                # Keep the longest/most complete document
                # representation if duplicates have different
                # document text.
                existing_doc = candidate.get("doc", "")

                if len(str(document)) > len(str(existing_doc)):
                    candidate["doc"] = document

    # =========================================================
    # 4. Candidate fusion
    # =========================================================

    print()
    # print("=" * 90)
    # print("CPC MULTI-PASS FUSION")
    # print("=" * 90)

    # print(
    #     "Structural candidates :",
    #     len([c for c in unique_candidates.values() if "STRUCTURAL" in c["retrieved_from"]]),
    # )

    # print(
    #     "Procedural candidates :",
    #     len([c for c in unique_candidates.values() if "PROCEDURAL" in c["retrieved_from"]]),
    # )

    # print(
    #     "Functional candidates :",
    #     len([c for c in unique_candidates.values() if "FUNCTIONAL" in c["retrieved_from"]]),
    # )

    # print(
    #     "Unique candidates     :",
    #     len(unique_candidates),
    # )

    if not unique_candidates:
        raise RuntimeError("CPC multi-pass retrieval returned zero candidates.")

    # =========================================================
    # 5. Build FULL invention context for CrossEncoder
    #
    # test_cpc_db.py uses the full abstract as the second-stage
    # reranking context.
    #
    # Here we use the complete structured invention.
    # =========================================================

    full_invention_context = _safe_join(
        [
            invention.invention_summary,
            "STRUCTURAL FEATURES:",
            structural_text,
            "PROCEDURAL FEATURES:",
            procedural_text,
            "FUNCTIONAL FEATURES:",
            functional_text,
        ]
    )

    if not full_invention_context.strip():
        raise RuntimeError("Unable to construct invention context for CPC reranking.")

    # =========================================================
    # 6. Cross-Encoder re-ranking
    #
    # Every unique CPC candidate is compared against the
    # complete invention context.
    # =========================================================

    cpc_codes = list(unique_candidates.keys())

    rerank_pairs = []

    for cpc_code in cpc_codes:
        candidate = unique_candidates[cpc_code]

        candidate_document = str(candidate.get("doc", "")).strip()

        # Prefer CPC title if the stored document is empty.
        if not candidate_document:
            candidate_document = candidate["title"]

        rerank_pairs.append(
            [
                full_invention_context,
                candidate_document,
            ]
        )

    # print()
    # print("=" * 90)
    # print("CPC CROSS-ENCODER RE-RANKING")
    # print("=" * 90)

    # print("Candidates sent to reranker:", len(rerank_pairs))

    # ---------------------------------------------------------
    # BGE CrossEncoder scoring
    # ---------------------------------------------------------
    rerank_scores = cross_encoder.predict(rerank_pairs)

    # =========================================================
    # 7. Sort all fused candidates by CrossEncoder score
    # =========================================================

    reranked_candidates = []
    for index, cpc_code in enumerate(cpc_codes):
        candidate = unique_candidates[cpc_code]
        reranked_candidates.append(
            {
                "cpc_code": cpc_code,
                "title": candidate["title"],
                "confidence_score": float(rerank_scores[index]),
                "retrieved_from": candidate["retrieved_from"],
                "retrieval_ranks": candidate["retrieval_ranks"],
                "metadata": candidate["metadata"],
            }
        )

    reranked_candidates.sort(key=lambda item: item["confidence_score"], reverse=True)

    # =========================================================
    # 8. Take FINAL TOP 15
    # =========================================================

    FINAL_TOP_K = 15
    final_candidates = reranked_candidates[:FINAL_TOP_K]

    # print()
    # print("=" * 90)
    # print("FINAL TOP 15 CPC CLASSIFICATIONS")
    # print("=" * 90)

    # for rank, candidate in enumerate(final_candidates,start=1):
    #     print()
    #     print(f"{rank:2}. {candidate['cpc_code']}")

    #     print(f"    {candidate['title']}")

    #     print(f"    Score: {candidate['confidence_score']:.6f}")

    #     print("    Retrieved from: " + ", ".join(candidate["retrieved_from"]))

    # =========================================================
    # 9. Convert to your existing CPCAnalysis model
    #
    # We do NOT use an LLM here.
    #
    # CPC code/title come directly from the CPC corpus.
    # =========================================================

    cpc_analysis_candidates = []

    for candidate in final_candidates:
        cpc_analysis_candidates.append(
            {
                "cpc_code": candidate["cpc_code"],
                "title": candidate["title"],
                "feature_id": None,
                "relevance": "MEDIUM",
                "reason": ("Retrieved independently through structural/procedural/functional CPC semantic searches and selected by CrossEncoder reranking."),
            }
        )

    # ---------------------------------------------------------
    # Construct CPCAnalysis.
    #
    # This assumes the existing CPCAnalysis model accepts
    # candidate dictionaries in the same way your previous
    # implementation does.
    # ---------------------------------------------------------

    final_result = CPCAnalysis(candidates=cpc_analysis_candidates)

    # =========================================================
    # 10. Audit
    # =========================================================

    audit = context.audit
    if audit is not None:
        function_name = inspect.currentframe().f_code.co_name
        audit.log_model_call(
            thread_id,
            function_name,
            (f"CPC multi-pass retrieval + CrossEncoder reranking. Structural={RETRIEVAL_TOP_K}, Procedural={RETRIEVAL_TOP_K}, Functional={RETRIEVAL_TOP_K}, Final={len(final_candidates)}."),
            final_result,
        )

    # print()
    # print("=" * 90)
    # print("LOOKUP_CPC COMPLETE")
    # print("=" * 90)

    return {"cpc_analysis": final_result}


# ****************************************************************************************************************************************
# *                                                   USPTO queries
# ****************************************************************************************************************************************


def _clean_uspto_term(term: Any) -> str:
    """
    Clean a keyword before placing it in a USPTO query.
    """

    if term is None:
        return ""

    term = str(term).strip()

    if not term:
        return ""

    # Remove surrounding quotes if the keyword generator
    # already supplied them.
    if len(term) >= 2:
        if (term.startswith('"') and term.endswith('"')) or (term.startswith("'") and term.endswith("'")):
            term = term[1:-1].strip()

    return term


def _format_uspto_term(term: Any) -> str:
    """
    Format one keyword for USPTO Advanced Search.

    Multi-word terms are quoted.
    Single-word terms are left unquoted.
    """

    term = _clean_uspto_term(term)

    if not term:
        return ""

    if " " in term:
        return f'"{term}"'

    return term


def _build_keyword_group(keyword_set: Any) -> str:
    """
    Convert one KeywordSet into an OR expression.

    Example:

    ("immersion cooling"
     OR "submersion cooling"
     OR "immersion-based cooling")
    """

    terms = []

    sources = [
        getattr(keyword_set, "primary_keywords", []),
        getattr(keyword_set, "synonyms", []),
        getattr(keyword_set, "alternative_terms", []),
    ]

    seen = set()

    for source in sources:
        for term in source:
            cleaned = _clean_uspto_term(term)

            if not cleaned:
                continue

            normalized = cleaned.casefold()

            if normalized in seen:
                continue

            seen.add(normalized)

            terms.append(_format_uspto_term(cleaned))

    if not terms:
        return ""

    if len(terms) == 1:
        return terms[0]

    return "(" + " OR ".join(terms) + ")"


def _build_keyword_expression(
    keyword_sets: list[Any],
) -> str:
    """
    Combine KeywordSets into a USPTO Boolean expression.

    Terms belonging to the same KeywordSet are alternatives
    and therefore use OR.

    Different KeywordSets represent different technical
    concepts and therefore use AND.
    """

    groups = []

    for keyword_set in keyword_sets:
        group = _build_keyword_group(keyword_set)

        if group:
            groups.append(group)

    if not groups:
        return ""

    if len(groups) == 1:
        return groups[0]

    return "\nAND\n".join(groups)


def _build_cpc_expression(
    cpc_analysis: CPCAnalysis,
) -> str:
    """
    Build a USPTO CPC query from CPCAnalysis.

    CPC candidates are alternatives, so they are combined
    with OR.

    The CPC code is taken exactly from CPCAnalysis.
    """

    codes = []

    seen = set()

    for candidate in cpc_analysis.candidates:
        code = getattr(candidate, "cpc_code", None)
        if not code:
            continue
        code = str(code).strip()
        if not code:
            continue

        normalized = code.casefold()

        if normalized in seen:
            continue

        seen.add(normalized)

        codes.append(f"{code}.CPC.")

    if not codes:
        return ""

    if len(codes) == 1:
        return codes[0]

    return "(" + " OR ".join(codes) + ")"


def generate_uspto_queries(state: PatentState, config: RunnableConfig) -> dict:
    """
    Generate executable USPTO Patent Public Search queries.
    Four independent search paths are generated:
        TITLE
        DESCRIPTION
        CLAIMS
        CPC
    KeywordAnalysis supplies the text-search terminology.
    CPCAnalysis supplies the CPC classifications.
    No LLM is used in this node because this node performs
    deterministic transformation into USPTO search syntax.
    """
    configurable = config.get("configurable", {})

    context = configurable.get("context")
    thread_id = configurable.get("thread_id")

    if context is None:
        raise ValueError("Application context was not passed in runtime config.")

    audit = context.audit
    # =========================================================
    # Retrieve state
    # =========================================================
    keywords = state.get("keywords")
    cpc_analysis = state.get("cpc_analysis")
    if keywords is None:
        raise ValueError("KeywordAnalysis is missing from state. generate_keywords must execute before generate_uspto_queries.")
    if cpc_analysis is None:
        raise ValueError("CPCAnalysis is missing from state. lookup_cpc must execute before generate_uspto_queries.")
    # =========================================================
    # Combine ALL keyword categories
    # =========================================================
    keyword_sets = list(keywords.structural_keywords) + list(keywords.procedural_keywords) + list(keywords.functional_keywords)
    if not keyword_sets:
        raise RuntimeError("KeywordAnalysis contains no keyword sets.")

    # =========================================================
    # Build text expression
    # =========================================================
    text_expression = _build_keyword_expression(keyword_sets)
    if not text_expression:
        raise RuntimeError("KeywordAnalysis contains no usable search terms.")

    # =========================================================
    # Build CPC expression
    # =========================================================
    cpc_expression = _build_cpc_expression(cpc_analysis)
    if not cpc_expression:
        raise RuntimeError("CPCAnalysis contains no usable CPC codes.")

    # =========================================================
    # Construct four USPTO queries
    # =========================================================
    result = USPTOQueryAnalysis(
        queries=[
            USPTOQuery(
                query_name="TITLE",
                query=f"({text_expression}).TI.",
                purpose=("Search patent titles using the technical terminology generated from the invention."),
                priority="HIGH",
            ),
            USPTOQuery(
                query_name="DESCRIPTION",
                query=f"({text_expression}).SPEC.",
                purpose=("Search patent descriptions/specifications using the technical terminology generated from the invention."),
                priority="HIGH",
            ),
            USPTOQuery(
                query_name="CLAIMS",
                query=f"({text_expression}).CLM.",
                purpose=("Search patent claims using the technical terminology generated from the invention."),
                priority="HIGH",
            ),
            USPTOQuery(
                query_name="CPC",
                query=cpc_expression,
                purpose=("Search patent documents using the CPC classifications identified during CPC analysis."),
                priority="HIGH",
            ),
        ]
    )
    # =========================================================
    # Audit
    # =========================================================
    if audit is not None:
        function_name = inspect.currentframe().f_code.co_name
        audit.log_model_call(thread_id, function_name, ("Deterministic USPTO query generation from KeywordAnalysis and CPCAnalysis."), result)

    # =========================================================
    # Diagnostics
    # =========================================================

    print()
    print("=" * 90)
    print("USPTO QUERY NODE")
    print("=" * 90)

    for query in result.queries:
        print()
        print(f"QUERY NAME : {query.query_name}")
        print(f"QUERY      : {query.query}")
        print(f"PURPOSE    : {query.purpose}")
        print(f"PRIORITY   : {query.priority}")

    print()
    print("=" * 90)

    return {"uspto_queries": result}


# ****************************************************************************************************************************************
# *                                                   Espacenet queries
# ****************************************************************************************************************************************


def _clean_espacenet_term(term: Any) -> str:
    if term is None:
        return ""
    term = str(term).strip()
    if not term:
        return ""

    # Remove existing surrounding quotes.
    if len(term) >= 2:
        if (term.startswith('"') and term.endswith('"')) or (term.startswith("'") and term.endswith("'")):
            term = term[1:-1].strip()
    return term


def _format_espacenet_term(term: Any) -> str:
    term = _clean_espacenet_term(term)
    if not term:
        return ""
    # Treat multi-word technical terms as phrases.
    if " " in term:
        return f'"{term}"'
    return term


def _build_espacenet_keyword_group(keyword_set: Any) -> str:
    terms = []
    sources = [
        getattr(keyword_set, "primary_keywords", []),
        getattr(keyword_set, "synonyms", []),
        getattr(keyword_set, "alternative_terms", []),
    ]
    seen = set()
    for source in sources:
        for term in source:
            cleaned = _clean_espacenet_term(term)
            if not cleaned:
                continue
            normalized = cleaned.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            terms.append(_format_espacenet_term(cleaned))
    if not terms:
        return ""
    if len(terms) == 1:
        return terms[0]
    return "(" + " OR ".join(terms) + ")"


def _build_espacenet_keyword_expression(keyword_sets: list[Any]) -> str:
    groups = []
    for keyword_set in keyword_sets:
        group = _build_espacenet_keyword_group(keyword_set)
        if group:
            groups.append(group)

    if not groups:
        return ""
    if len(groups) == 1:
        return groups[0]
    return "\nAND\n".join(groups)


def _build_espacenet_cpc_expression(cpc_analysis: CPCAnalysis) -> str:
    codes = []
    seen = set()
    for candidate in cpc_analysis.candidates:
        code = getattr(candidate, "cpc_code", None)
        if not code:
            continue
        code = str(code).strip()
        if not code:
            continue
        normalized = code.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        codes.append(code)
    if not codes:
        return ""
    if len(codes) == 1:
        return codes[0]
    return "(" + " OR ".join(codes) + ")"


def generate_espacenet_queries(state: PatentState, config: RunnableConfig) -> dict:
    configurable = config.get("configurable", {})

    context = configurable.get("context")
    thread_id = configurable.get("thread_id")
    if context is None:
        raise ValueError("Application context was not passed in runtime config.")
    audit = context.audit
    keywords = state.get("keywords")
    cpc_analysis = state.get("cpc_analysis")
    if keywords is None:
        raise ValueError("KeywordAnalysis is missing from state. generate_keywords must execute before generate_espacenet_queries.")
    if cpc_analysis is None:
        raise ValueError("CPCAnalysis is missing from state. lookup_cpc must execute before generate_espacenet_queries.")
    # ---------------------------------------------------------
    # Combine all keyword sets
    # ---------------------------------------------------------
    keyword_sets = list(keywords.structural_keywords) + list(keywords.procedural_keywords) + list(keywords.functional_keywords)
    if not keyword_sets:
        raise RuntimeError("KeywordAnalysis contains no keyword sets.")
    # ---------------------------------------------------------
    # Build text expression
    # ---------------------------------------------------------
    text_expression = _build_espacenet_keyword_expression(keyword_sets)
    if not text_expression:
        raise RuntimeError("KeywordAnalysis contains no usable search terms.")

    # ---------------------------------------------------------
    # Build CPC expression
    # ---------------------------------------------------------
    cpc_expression = _build_espacenet_cpc_expression(cpc_analysis)
    if not cpc_expression:
        raise RuntimeError("CPCAnalysis contains no usable CPC codes.")

    # ---------------------------------------------------------
    # Construct exactly four Espacenet queries
    # ---------------------------------------------------------
    result = EspacenetQueryAnalysis(
        queries=[
            EspacenetQuery(
                query_name="TITLE",
                query=f"ti=({text_expression})",
                purpose=("Search patent titles using the technical terminology generated from the invention."),
                priority="HIGH",
            ),
            EspacenetQuery(
                query_name="DESCRIPTION",
                query=f"desc=({text_expression})",
                purpose=("Search patent descriptions using the technical terminology generated from the invention."),
                priority="HIGH",
            ),
            EspacenetQuery(
                query_name="CLAIMS",
                query=f"claims=({text_expression})",
                purpose=("Search patent claims using the technical terminology generated from the invention."),
                priority="HIGH",
            ),
            EspacenetQuery(
                query_name="CPC",
                query=f"cpc={cpc_expression}",
                purpose=("Search patent documents using the CPC classifications identified during CPC analysis."),
                priority="HIGH",
            ),
        ]
    )

    # Audit
    if audit is not None:
        function_name = inspect.currentframe().f_code.co_name

        audit.log_model_call(thread_id, function_name, ("Deterministic Espacenet query generation from KeywordAnalysis and CPCAnalysis."), result)

    # ---------------------------------------------------------
    # Diagnostic output
    # ---------------------------------------------------------

    print()
    print("=" * 90)
    print("ESPACENET QUERY NODE **---------- GG ----------**")
    print("=" * 90)

    for query in result.queries:
        print()
        print(f"QUERY NAME : {query.query_name}")
        print(f"QUERY      : {query.query}")
        print(f"PURPOSE    : {query.purpose}")
        print(f"PRIORITY   : {query.priority}")

    print()
    print("=" * 90)
    return {"espacenet_queries": result}


# ****************************************************************************************************************************************
# *                                                   Client report
# ****************************************************************************************************************************************


def create_client_report(state: PatentState, config: RunnableConfig) -> dict:
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
