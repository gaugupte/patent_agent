"""Asynchronous three-source NPL discovery and LLM relevance ranking.

Providers: Semantic Scholar, OpenAlex, and arXiv.
Requires: httpx (pip install httpx).
Designed as an async LangGraph node. No full-text downloads are performed.
"""
from __future__ import annotations

import asyncio
import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlencode

import httpx
from langchain_core.runnables import RunnableConfig

from config.state import PatentState

FEATURE_LIMIT = 8
RESULTS_PER_QUERY = 20
RERANK_CANDIDATE_LIMIT = 50
RERANK_BATCH_SIZE = 10
HTTP_TIMEOUT_SECONDS = 20.0
SEMANTIC_SCHOLAR_MAX_RETRIES = 4
USER_AGENT = "PatentAgentNPL/2.0 (scholarly discovery)"

CATEGORIES = (
    ("structural", "structural_features"),
    ("procedural", "procedural_features"),
    ("functional", "functional_features"),
)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _feature_text(feature: Any) -> str:
    values = [_get(feature, k) for k in ("feature", "step", "function", "details", "description")]
    text = ". ".join(str(v).strip() for v in values if v and str(v).strip())
    return re.sub(r"\s+", " ", text).strip()


def _feature_id(feature: Any) -> str:
    return str(_get(feature, "feature_id", "") or "").strip()


def _features_by_category(invention: Any) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {}
    for category, attr in CATEGORIES:
        features = list(_get(invention, attr, []) or [])[:FEATURE_LIMIT]
        result[category] = [
            {"feature_id": _feature_id(item), "text": _feature_text(item)}
            for item in features if _feature_text(item)
        ]
    return result


def _compact(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip(" .;,\t\n")
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0]
    return text


def _fallback_query_plan(features: dict[str, list[dict[str, str]]]) -> list[dict[str, Any]]:
    """Deterministic fallback if the configured LLM cannot produce a query plan."""
    plan = []
    for category, items in features.items():
        if not items:
            continue
        texts = [_compact(item["text"], 160) for item in items]
        # Semantic Scholar is plain-text only; do not send Boolean operators there.
        semantic_query = "; ".join(texts[:4])[:700]
        # Synonym-like academic query: preserve technical phrases and OR them.
        phrases = []
        for text in texts:
            phrase = re.sub(r"[^\w\s-]", " ", text)
            phrase = re.sub(r"\s+", " ", phrase).strip()
            if phrase and phrase.lower() not in {p.lower() for p in phrases}:
                phrases.append(phrase[:100])
        concept_query = " OR ".join(f'"{p}"' for p in phrases[:6])[:700]
        # arXiv supports fielded query syntax and AND/OR. Keep it bounded.
        core = []
        for text in texts[:3]:
            words = [w for w in re.findall(r"[A-Za-z0-9]+", text) if len(w) > 3]
            if words:
                core.append(" AND ".join(f'all:"{w}"' for w in words[:4]))
        arxiv_query = " OR ".join(f"({q})" for q in core)[:700]
        plan.append({
            "category": category,
            "feature_ids": [x["feature_id"] for x in items if x["feature_id"]],
            "feature_texts": texts,
            "semantic_scholar_query": semantic_query,
            "openalex_concept_query": concept_query or semantic_query,
            "arxiv_boolean_query": arxiv_query or "all:" + json.dumps(semantic_query[:150]),
            "query_plan_method": "deterministic_fallback",
        })
    return plan


def _parse_json_content(content: Any) -> Any:
    if isinstance(content, list):
        content = "".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in content)
    text = str(content or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


async def _llm_query_plan(context: Any, features: dict[str, list[dict[str, str]]]) -> list[dict[str, Any]]:
    llm = getattr(context, "llm", None) if context is not None else None
    if llm is None or not hasattr(llm, "ainvoke"):
        return _fallback_query_plan(features)

    prompt = f"""You are designing scholarly non-patent-literature search queries for a patent-prior-art discovery tool.
Return ONLY valid JSON: {{"queries":[{{"category":"structural|procedural|functional","semantic_scholar_query":"...","openalex_concept_query":"...","arxiv_boolean_query":"..."}}]}}.
For every non-empty category in the input, return exactly one query object.
Rules:
- Semantic Scholar query: natural language, concise technical meaning, no Boolean syntax; retain important mechanisms and domain context.
- OpenAlex query: concise academic terminology and synonym variants, using quoted phrases and OR where useful. It is still a text query, not a guarantee of concept-vector matching.
- arXiv query: valid arXiv advanced-search syntax using fields such as ti:, abs:, and all:, plus AND/OR and parentheses. Avoid unsupported wildcard assumptions. Keep queries focused; do not include generic words alone.
- Do not invent features, mechanisms, or synonyms unsupported by the feature descriptions.
- Query breadth should favor relevant papers over maximal result volume.
Input feature matrix:
{json.dumps(features, ensure_ascii=False)}"""
    try:
        response = await llm.ainvoke(prompt)
        content = getattr(response, "content", response)
        parsed = _parse_json_content(content)
        raw_queries = parsed.get("queries", [])
        by_category = {str(q.get("category", "")).lower(): q for q in raw_queries if isinstance(q, dict)}
        plan = []
        for category, items in features.items():
            if not items:
                continue
            q = by_category.get(category, {})
            fallback = _fallback_query_plan({category: items})[0]
            plan.append({
                **fallback,
                "semantic_scholar_query": _compact(q.get("semantic_scholar_query") or fallback["semantic_scholar_query"], 700),
                "openalex_concept_query": _compact(q.get("openalex_concept_query") or fallback["openalex_concept_query"], 700),
                "arxiv_boolean_query": _compact(q.get("arxiv_boolean_query") or fallback["arxiv_boolean_query"], 700),
                "query_plan_method": "llm",
            })
        return plan
    except Exception as exc:
        print(f"NPL query-plan LLM failed; using fallback queries: {exc}")
        return _fallback_query_plan(features)


def _normalize_doi(value: Any) -> str:
    if not value:
        return ""
    value = str(value).strip().lower()
    value = re.sub(r"^https?://(dx\.)?doi\.org/", "", value)
    return value.strip().rstrip(".,; ")


def _normalize_title(value: Any) -> str:
    value = str(value or "").casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _arxiv_id(value: Any) -> str:
    if not value:
        return ""
    text = str(value).strip()
    text = re.sub(r"^https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/", "", text, flags=re.I)
    text = re.sub(r"\.pdf$", "", text, flags=re.I)
    return text.split("v")[0].strip().lower()


def _normalize_record(*, title: str, authors: list[str], date: str | None, abstract: str | None,
                      doi: Any, url: str | None, provider: str, record_id: str | None,
                      category: str, feature_ids: list[str], tldr: str | None = None,
                      arxiv_id: str | None = None, venue: str | None = None,
                      document_type: str | None = None, updated_date: str | None = None) -> dict[str, Any] | None:
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    if not title:
        return None
    clean_doi = _normalize_doi(doi)
    return {
        "title": title,
        "authors": authors or [],
        "publication_date": date,
        "updated_date": updated_date,
        "document_type": document_type,
        "abstract": re.sub(r"\s+", " ", html.unescape(str(abstract or ""))).strip() or None,
        "tldr": re.sub(r"\s+", " ", html.unescape(str(tldr or ""))).strip() or None,
        "doi": clean_doi or None,
        "arxiv_id": _arxiv_id(arxiv_id) or None,
        "url": url or (f"https://doi.org/{clean_doi}" if clean_doi else None),
        "venue": venue,
        "source_provider": provider,
        "provider_record_id": record_id,
        "searched_feature_ids": list(feature_ids),
        "search_category": category,
    }


async def _get_json(client: httpx.AsyncClient, url: str, params: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    response = await client.get(url, params=params, headers=headers)
    response.raise_for_status()
    return response.json()


async def _semantic_scholar_get_json(
    client: httpx.AsyncClient,
    params: dict[str, Any],
    headers: dict[str, str],
    request_lock: asyncio.Lock,
    rate_state: dict[str, float],
) -> dict[str, Any]:
    """Serialize Semantic Scholar requests and retry transient 429 responses."""
    api_key_present = bool(os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip())
    # Conservative spacing: API-key requests around 1 request/sec; without a key,
    # slow down further because unauthenticated traffic shares a public pool.
    default_interval = 1.1 if api_key_present else 3.5
    min_interval = max(0.0, float(os.getenv("SEMANTIC_SCHOLAR_MIN_INTERVAL_SECONDS", default_interval)))
    url = "https://api.semanticscholar.org/graph/v1/paper/search"

    for attempt in range(SEMANTIC_SCHOLAR_MAX_RETRIES + 1):
        async with request_lock:
            elapsed = time.monotonic() - rate_state.get("last_request_at", 0.0)
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            response = await client.get(url, params=params, headers=headers)
            rate_state["last_request_at"] = time.monotonic()

        if response.status_code == 429:
            if attempt >= SEMANTIC_SCHOLAR_MAX_RETRIES:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After", "").strip()
            try:
                wait_seconds = float(retry_after)
            except (TypeError, ValueError):
                wait_seconds = min(5.0 * (2 ** attempt), 60.0)
            # Avoid a tight retry loop, and cap server-provided delays to a practical
            # maximum per attempt. A later retry may still be rate-limited.
            wait_seconds = max(1.0, min(wait_seconds, 120.0))
            await asyncio.sleep(wait_seconds)
            continue

        response.raise_for_status()
        return response.json()

    raise RuntimeError("Semantic Scholar retries exhausted")


async def _search_semantic_scholar(
    client: httpx.AsyncClient,
    item: dict[str, Any],
    request_lock: asyncio.Lock,
    rate_state: dict[str, float],
) -> dict[str, Any]:
    started = time.monotonic()
    provider, category = "Semantic Scholar", item["category"]
    try:
        headers = {}
        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
        if api_key:
            headers["x-api-key"] = api_key
        payload = await _semantic_scholar_get_json(client, {
            "query": item["semantic_scholar_query"],
            "limit": RESULTS_PER_QUERY,
            "fields": "title,abstract,tldr,year,publicationDate,authors,externalIds,url,venue,publicationTypes,openAccessPdf",
        }, headers, request_lock, rate_state)
        results = []
        for paper in payload.get("data", []):
            ids = paper.get("externalIds") or {}
            tldr = paper.get("tldr")
            if isinstance(tldr, dict):
                tldr = tldr.get("text")
            authors = [a.get("name", "") for a in paper.get("authors", []) if a.get("name")]
            normalized = _normalize_record(
                title=paper.get("title", ""), authors=authors,
                date=paper.get("publicationDate") or (str(paper.get("year")) if paper.get("year") else None),
                abstract=paper.get("abstract"), tldr=tldr,
                doi=ids.get("DOI"), arxiv_id=ids.get("ArXiv"), url=paper.get("url"),
                provider=provider, record_id=paper.get("paperId"), category=category,
                feature_ids=item["feature_ids"], venue=paper.get("venue"),
                document_type=",".join(paper.get("publicationTypes") or []) or None,
            )
            if normalized:
                oa_pdf = paper.get("openAccessPdf") or {}
                normalized["open_access_url"] = oa_pdf.get("url")
                results.append(normalized)
        return _outcome(provider, category, results, started)
    except Exception as exc:
        return _error_outcome(provider, category, started, exc)


async def _search_openalex(client: httpx.AsyncClient, item: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    provider, category = "OpenAlex", item["category"]
    try:
        params: dict[str, Any] = {
            "search": item["openalex_concept_query"],
            "per-page": RESULTS_PER_QUERY,
            "select": "id,doi,title,publication_year,publication_date,type,authorships,primary_location,best_oa_location,open_access,abstract_inverted_index,ids,topics,keywords",
        }
        api_key = os.getenv("OPENALEX_API_KEY", "").strip()
        if api_key:
            params["api_key"] = api_key
        payload = await _get_json(client, "https://api.openalex.org/works", params)
        results = []
        for work in payload.get("results", []):
            authors = []
            for authorship in work.get("authorships") or []:
                name = (authorship.get("author") or {}).get("display_name")
                if name:
                    authors.append(name)
            inv = work.get("abstract_inverted_index") or {}
            positions: dict[int, str] = {}
            for token, indexes in inv.items():
                for index in indexes if isinstance(indexes, list) else []:
                    if isinstance(index, int):
                        positions[index] = token
            abstract = " ".join(positions[i] for i in sorted(positions)) if positions else None
            location = work.get("primary_location") or {}
            source = location.get("source") or {}
            oa = work.get("open_access") or {}
            best_oa = work.get("best_oa_location") or {}
            doi = work.get("doi") or (work.get("ids") or {}).get("doi")
            normalized = _normalize_record(
                title=work.get("title", ""), authors=authors,
                date=work.get("publication_date") or (str(work.get("publication_year")) if work.get("publication_year") else None),
                abstract=abstract, doi=doi,
                url=location.get("landing_page_url") or best_oa.get("landing_page_url") or oa.get("oa_url") or work.get("id"),
                provider=provider, record_id=work.get("id"), category=category,
                feature_ids=item["feature_ids"], venue=source.get("display_name"), document_type=work.get("type"),
            )
            if normalized:
                normalized["open_access_url"] = oa.get("oa_url") or best_oa.get("pdf_url")
                normalized["openalex_topics"] = [x.get("display_name") for x in work.get("topics", []) if x.get("display_name")]
                normalized["openalex_keywords"] = [x.get("display_name") for x in work.get("keywords", []) if x.get("display_name")]
                results.append(normalized)
        return _outcome(provider, category, results, started)
    except Exception as exc:
        return _error_outcome(provider, category, started, exc)


async def _search_arxiv(client: httpx.AsyncClient, item: dict[str, Any]) -> dict[str, Any]:
    started = time.monotonic()
    provider, category = "arXiv", item["category"]
    try:
        # arXiv returns Atom XML, so parse the feed rather than expecting JSON.
        payload = await client.get("https://export.arxiv.org/api/query", params={
            "search_query": item["arxiv_boolean_query"],
            "start": 0,
            "max_results": RESULTS_PER_QUERY,
            "sortBy": "relevance",
            "sortOrder": "descending",
        })
        payload.raise_for_status()
        root = ET.fromstring(payload.text)
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        results = []
        for entry in root.findall("atom:entry", ns):
            title = " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split())
            abstract = " ".join((entry.findtext("atom:summary", default="", namespaces=ns) or "").split())
            entry_id = entry.findtext("atom:id", default="", namespaces=ns)
            authors = [a.findtext("atom:name", default="", namespaces=ns) for a in entry.findall("atom:author", ns)]
            doi = entry.findtext("arxiv:doi", default="", namespaces=ns)
            published = entry.findtext("atom:published", default="", namespaces=ns) or None
            updated = entry.findtext("atom:updated", default="", namespaces=ns) or None
            normalized = _normalize_record(
                title=title, authors=authors, date=published[:10] if published else None,
                updated_date=updated[:10] if updated else None, abstract=abstract, doi=doi,
                arxiv_id=entry_id, url=entry_id or None, provider=provider,
                record_id=entry_id, category=category, feature_ids=item["feature_ids"],
                document_type="preprint",
            )
            if normalized:
                normalized["arxiv_submitted_date"] = published[:10] if published else None
                normalized["arxiv_updated_date"] = updated[:10] if updated else None
                results.append(normalized)
        return _outcome(provider, category, results, started)
    except Exception as exc:
        return _error_outcome(provider, category, started, exc)


def _outcome(provider: str, category: str, results: list[dict[str, Any]], started: float) -> dict[str, Any]:
    return {"provider": provider, "category": category, "results": results, "count": len(results),
            "elapsed_seconds": round(time.monotonic() - started, 3), "error": None}


def _error_outcome(provider: str, category: str, started: float, exc: Exception) -> dict[str, Any]:
    return {"provider": provider, "category": category, "results": [], "count": 0,
            "elapsed_seconds": round(time.monotonic() - started, 3), "error": f"{type(exc).__name__}: {exc}"}


def _deduplicate(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    key_to_index: dict[str, int] = {}
    for record in results:
        doi = _normalize_doi(record.get("doi"))
        arxiv = _arxiv_id(record.get("arxiv_id"))
        title = _normalize_title(record.get("title"))
        authors = record.get("authors") or []
        first_author = _normalize_title(authors[0]) if authors else ""
        key = f"doi:{doi}" if doi else (f"arxiv:{arxiv}" if arxiv else (f"title-author:{title}|{first_author}" if title else ""))
        if not key or key not in key_to_index:
            item = dict(record)
            item["source_providers"] = [record["source_provider"]] if record.get("source_provider") else []
            item["source_urls"] = [record["url"]] if record.get("url") else []
            item["search_categories"] = [record["search_category"]] if record.get("search_category") else []
            item["searched_feature_ids"] = list(dict.fromkeys(record.get("searched_feature_ids") or []))
            if key:
                key_to_index[key] = len(merged)
            merged.append(item)
            continue
        existing = merged[key_to_index[key]]
        for field, value in (("source_providers", record.get("source_provider")),
                             ("source_urls", record.get("url")),
                             ("search_categories", record.get("search_category"))):
            if value and value not in existing.setdefault(field, []):
                existing[field].append(value)
        for fid in record.get("searched_feature_ids") or []:
            if fid and fid not in existing["searched_feature_ids"]:
                existing["searched_feature_ids"].append(fid)
        # Keep the richer abstract/TLDR and fill metadata gaps.
        for field in ("abstract", "tldr", "publication_date", "updated_date", "venue", "open_access_url", "doi", "arxiv_id"):
            if not existing.get(field) and record.get(field):
                existing[field] = record[field]
        for field in ("openalex_topics", "openalex_keywords"):
            for value in record.get(field, []):
                if value not in existing.setdefault(field, []):
                    existing[field].append(value)
    return merged


def _pre_rank(record: dict[str, Any], feature_matrix: dict[str, list[dict[str, str]]]) -> float:
    """Cheap shortlist score before expensive LLM evaluation; not a final relevance score."""
    text = _normalize_title(" ".join([
        record.get("title") or "", record.get("abstract") or "", record.get("tldr") or "",
        " ".join(record.get("openalex_topics") or []), " ".join(record.get("openalex_keywords") or []),
    ]))
    score = 0.0
    for category, features in feature_matrix.items():
        category_hits = 0
        for feature in features:
            terms = [w for w in re.findall(r"[a-z0-9]+", feature["text"].lower()) if len(w) >= 5]
            if not terms:
                continue
            hits = sum(1 for term in set(terms) if term in text)
            if hits:
                category_hits += min(hits, 4)
        score += min(category_hits, 12)
    if record.get("abstract"):
        score += 1.0
    if record.get("tldr"):
        score += 0.5
    return score


def _llm_content(response: Any) -> str:
    return str(getattr(response, "content", response) or "")


async def _rerank_with_llm(context: Any, records: list[dict[str, Any]], feature_matrix: dict[str, list[dict[str, str]]]) -> tuple[list[dict[str, Any]], str]:
    llm = getattr(context, "llm", None) if context is not None else None
    if llm is None or not hasattr(llm, "ainvoke"):
        for record in records:
            record["relevance_score"] = round(record.get("pre_rank_score", 0.0), 2)
            record["relevance_ranking_method"] = "lexical_fallback_llm_unavailable"
        records.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return records, "llm_unavailable_lexical_fallback"

    feature_payload = {
        category: [{"feature_id": f.get("feature_id"), "feature": f.get("text")} for f in items]
        for category, items in feature_matrix.items()
    }
    for start in range(0, len(records), RERANK_BATCH_SIZE):
        batch = records[start:start + RERANK_BATCH_SIZE]
        papers = []
        for idx, record in enumerate(batch):
            papers.append({
                "candidate_id": idx,
                "title": record.get("title"),
                "abstract": (record.get("abstract") or "")[:5000],
                "semantic_scholar_tldr": (record.get("tldr") or "")[:1000],
                "publication_date": record.get("publication_date"),
            })
        prompt = f"""You are assisting a patent professional with preliminary non-patent literature discovery. This is triage, not a legal opinion.
Compare each paper's title, abstract and (when present) Semantic Scholar TLDR with the invention feature matrix.
Score each paper from 0 to 100 for technical relevance/overlap, not general topical similarity. A high score requires a meaningful match to one or more concrete features or mechanisms. Do not infer disclosure that is absent from the provided text. Missing abstracts/TLDR are not proof of irrelevance.
Return ONLY JSON: {{"evaluations":[{{"candidate_id":0,"score":0,"matched_feature_ids":[],"rationale":"short evidence-based explanation","evidence_phrases":[]}}]}}.
Use concise rationales. Evidence phrases must be short phrases copied from the supplied paper text. Do not make legal novelty/patentability conclusions.
Feature matrix:
{json.dumps(feature_payload, ensure_ascii=False)}
Candidates:
{json.dumps(papers, ensure_ascii=False)}"""
        try:
            response = await llm.ainvoke(prompt)
            parsed = _parse_json_content(_llm_content(response))
            evaluations = parsed.get("evaluations", [])
            for evaluation in evaluations:
                if not isinstance(evaluation, dict):
                    continue
                idx = evaluation.get("candidate_id")
                if not isinstance(idx, int) or idx < 0 or idx >= len(batch):
                    continue
                record = batch[idx]
                score = evaluation.get("score", 0)
                try:
                    score = max(0.0, min(100.0, float(score)))
                except (TypeError, ValueError):
                    score = 0.0
                record["relevance_score"] = round(score, 2)
                record["matched_feature_ids"] = evaluation.get("matched_feature_ids") or []
                record["relevance_rationale"] = str(evaluation.get("rationale") or "")[:1200]
                record["evidence_phrases"] = evaluation.get("evidence_phrases") or []
                record["relevance_ranking_method"] = "llm_feature_matrix"
        except Exception as exc:
            print(f"NPL LLM rerank batch failed: {exc}")
            for record in batch:
                if "relevance_score" not in record:
                    record["relevance_score"] = round(record.get("pre_rank_score", 0.0), 2)
                    record["matched_feature_ids"] = []
                    record["relevance_rationale"] = "LLM evaluation unavailable; showing preliminary lexical score."
                    record["evidence_phrases"] = []
                    record["relevance_ranking_method"] = "lexical_fallback_batch_error"

    records.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    for rank, record in enumerate(records, start=1):
        record["relevance_rank"] = rank
    return records, "llm_feature_matrix"


async def _search_npl_three_sources_async(state: PatentState, config: RunnableConfig) -> dict[str, Any]:
    """Search Semantic Scholar, OpenAlex and arXiv concurrently, deduplicate and rerank."""
    invention = state.get("invention")
    if invention is None:
        raise ValueError("InventionRepresentation is missing from state. Run decompose_invention first.")

    feature_matrix = _features_by_category(invention)
    if not any(feature_matrix.values()):
        summary = {"status": "no_features", "raw_result_count": 0, "deduplicated_count": 0, "provider_calls": []}
        return {"npl_queries": [], "npl_results": [], "npl_search_summary": summary}

    configurable = (config or {}).get("configurable", {})
    context = configurable.get("context")
    plan = await _llm_query_plan(context, feature_matrix)
    timeout = httpx.Timeout(HTTP_TIMEOUT_SECONDS, connect=10.0)
    limits = httpx.Limits(max_connections=12, max_keepalive_connections=6)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, application/atom+xml, application/xml"}
    async with httpx.AsyncClient(timeout=timeout, limits=limits, headers=headers, follow_redirects=True) as client:
        tasks = []
        # Share one lock/rate clock across every Semantic Scholar query in this run.
        # OpenAlex and arXiv remain concurrent with each other and with S2 waits.
        semantic_scholar_lock = asyncio.Lock()
        semantic_scholar_rate_state: dict[str, float] = {"last_request_at": 0.0}
        for item in plan:
            tasks.extend([
                _search_semantic_scholar(client, item, semantic_scholar_lock, semantic_scholar_rate_state),
                _search_openalex(client, item),
                _search_arxiv(client, item),
            ])
        # All provider/category requests are launched together; failures are isolated per source.
        outcomes = await asyncio.gather(*tasks, return_exceptions=False)

    raw_results = [record for outcome in outcomes for record in outcome["results"]]
    deduplicated = _deduplicate(raw_results)
    for record in deduplicated:
        record["pre_rank_score"] = round(_pre_rank(record, feature_matrix), 2)
    # Use lexical feature overlap only to shortlist up to 50 candidates for LLM evaluation.
    shortlist = sorted(deduplicated, key=lambda x: x.get("pre_rank_score", 0), reverse=True)[:RERANK_CANDIDATE_LIMIT]
    ranked, ranking_method = await _rerank_with_llm(context, shortlist, feature_matrix)
    ranked_ids = {id(record) for record in ranked}
    # Keep remaining deduplicated results available for audit/review, but mark them as not LLM-ranked.
    unranked = [record for record in deduplicated if id(record) not in ranked_ids]
    for record in unranked:
        record["relevance_score"] = None
        record["relevance_rank"] = None
        record["relevance_ranking_method"] = "not_in_top_50_candidates"
    final_results = ranked + unranked

    provider_calls = [{k: outcome[k] for k in ("provider", "category", "count", "elapsed_seconds", "error")} for outcome in outcomes]
    summary = {
        "status": "success" if raw_results else ("provider_error" if any(x["error"] for x in provider_calls) else "no_results"),
        "query_count": len(plan),
        "provider_request_count": len(outcomes),
        "raw_result_count": len(raw_results),
        "deduplicated_count": len(deduplicated),
        "duplicates_removed": len(raw_results) - len(deduplicated),
        "llm_rerank_candidate_count": len(shortlist),
        "llm_rerank_count": sum(1 for x in ranked if x.get("relevance_ranking_method") == "llm_feature_matrix"),
        "ranking_method": ranking_method,
        "provider_calls": sorted(provider_calls, key=lambda x: (x["provider"], x["category"])),
    }

    audit = getattr(context, "audit", None) if context is not None else None
    if audit is not None:
        try:
            audit_result = audit.log_model_call(
                configurable.get("thread_id"), "search_npl_three_sources",
                f"Concurrent Semantic Scholar/OpenAlex/arXiv searches across {len(plan)} feature categories", summary,
            )
            if hasattr(audit_result, "__await__"):
                await audit_result
        except Exception:
            # Audit failure should not discard search results.
            pass

    print(f"NPL search complete: {len(raw_results)} raw, {len(deduplicated)} unique, {len(shortlist)} rerank candidates.")
    return {"npl_queries": plan, "npl_results": final_results, "npl_search_summary": summary}

def search_npl_three_sources(state: PatentState, config: RunnableConfig) -> dict[str, Any]:
    """Synchronous LangGraph adapter for applications using graph.stream()/invoke().

    The provider requests still run concurrently inside the async implementation.
    This wrapper lets the existing synchronous graph call the node without changing
    the rest of the application's invocation model.
    """
    return asyncio.run(_search_npl_three_sources_async(state, config))
