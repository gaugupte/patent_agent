# graph/npl_search.py

import html
import json
import os
import re
import threading
import time

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from langchain_core.runnables import RunnableConfig

from config.state import PatentState


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NPL_FEATURE_LIMIT = 8
NPL_RESULTS_PER_QUERY = 10
NPL_HTTP_TIMEOUT_SECONDS = 15

_CROSSREF_REQUEST_LOCK = threading.Lock()
_CROSSREF_LAST_REQUEST_AT = 0.0


# ---------------------------------------------------------------------------
# Feature extraction and search-plan creation
# ---------------------------------------------------------------------------


def _get_value(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from either a dictionary or a Pydantic model."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _feature_text(feature: Any) -> str:
    """Extract a searchable description from an invention feature."""

    values = [
        _get_value(feature, "feature"),
        _get_value(feature, "step"),
        _get_value(feature, "function"),
        _get_value(feature, "details"),
        _get_value(feature, "description"),
    ]

    parts = [str(value).strip() for value in values if value and str(value).strip()]

    return re.sub(r"\s+", " ", ". ".join(parts)).strip()


def _feature_id(feature: Any) -> str:
    return str(_get_value(feature, "feature_id", "") or "").strip()


def _build_search_plan(invention: Any) -> list[dict[str, Any]]:
    """
    Create one consolidated search query per available feature category.

    Maximum: three category queries, each searched against both providers.
    """

    categories = [
        ("structural", "structural_features"),
        ("procedural", "procedural_features"),
        ("functional", "functional_features"),
    ]

    plan = []

    for category, attribute in categories:
        features = _get_value(invention, attribute, []) or []
        selected = []

        for feature in list(features)[:NPL_FEATURE_LIMIT]:
            description = _feature_text(feature)

            if not description:
                continue

            # Keep individual descriptions reasonably concise.
            if len(description) > 120:
                description = description[:120].rsplit(" ", 1)[0]

            selected.append(
                {
                    "feature_id": _feature_id(feature),
                    "text": description,
                }
            )

        if not selected:
            continue

        query_parts = list(dict.fromkeys(item["text"] for item in selected))

        # Keep the consolidated query bounded.
        query = " ".join(query_parts)[:900].strip()

        plan.append(
            {
                "category": category,
                "query": query,
                "feature_ids": list(dict.fromkeys(item["feature_id"] for item in selected if item["feature_id"])),
                "feature_count": len(selected),
            }
        )

    return plan


# ---------------------------------------------------------------------------
# HTTP and metadata helpers
# ---------------------------------------------------------------------------


def _get_json(url: str) -> dict[str, Any]:
    """Perform a JSON HTTP GET using the Python standard library."""

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "PatentAgentNPL/1.0",
        },
        method="GET",
    )

    with urlopen(
        request,
        timeout=NPL_HTTP_TIMEOUT_SECONDS,
    ) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return json.loads(response.read().decode(charset))


def _reconstruct_abstract(inverted_index: Any) -> str | None:
    """Reconstruct an OpenAlex abstract from its inverted index."""

    if not isinstance(inverted_index, dict):
        return None

    positions = {}

    for token, indexes in inverted_index.items():
        if not isinstance(indexes, list):
            continue

        for index in indexes:
            if isinstance(index, int) and index >= 0:
                positions[index] = token

    if not positions:
        return None

    return " ".join(positions[index] for index in sorted(positions))


def _strip_html(value: Any) -> str | None:
    """Remove HTML markup from Crossref abstract metadata."""

    if not value:
        return None

    text = re.sub(r"<[^>]+>", " ", str(value))
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()

    return text or None


def _normalize_doi(value: Any) -> str:
    """Normalize DOI values for duplicate detection."""

    if not value:
        return ""

    doi = str(value).strip().lower()
    doi = re.sub(
        r"^https?://(dx\.)?doi\.org/",
        "",
        doi,
    )

    return doi.rstrip(".,; ")


def _normalize_title(value: Any) -> str:
    """Normalize titles for duplicate detection when DOI is unavailable."""

    title = str(value or "").casefold()
    title = re.sub(r"[^a-z0-9]+", " ", title)

    return re.sub(r"\s+", " ", title).strip()


def _provider_error(
    provider: str,
    category: str,
    started: float,
    exc: Exception,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "category": category,
        "results": [],
        "count": 0,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "error": f"{type(exc).__name__}: {exc}",
    }


# ---------------------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------------------


def _normalize_openalex_work(
    work: dict[str, Any],
    plan_item: dict[str, Any],
) -> dict[str, Any] | None:

    title = str(work.get("title") or "").strip()

    if not title:
        return None

    authors = []

    for authorship in work.get("authorships") or []:
        author = (authorship or {}).get("author") or {}
        name = author.get("display_name")

        if name:
            authors.append(name)

    location = work.get("primary_location") or {}
    source = location.get("source") or {}
    open_access = work.get("open_access") or {}
    best_location = work.get("best_oa_location") or {}
    ids = work.get("ids") or {}

    doi = work.get("doi") or ids.get("doi")

    url = location.get("landing_page_url") or best_location.get("landing_page_url") or open_access.get("oa_url") or doi or work.get("id")

    return {
        "title": title,
        "authors": authors,
        "publication_date": (work.get("publication_date") or work.get("publication_year")),
        "document_type": work.get("type"),
        "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),
        "doi": doi,
        "url": url,
        "venue": source.get("display_name"),
        "source_provider": "OpenAlex",
        "provider_record_id": work.get("id"),
        "open_access_url": (open_access.get("oa_url") or best_location.get("pdf_url")),
        "searched_feature_ids": list(plan_item["feature_ids"]),
        "search_category": plan_item["category"],
    }


def _search_openalex(
    plan_item: dict[str, Any],
) -> dict[str, Any]:

    started = time.monotonic()

    try:
        params = {
            "search": plan_item["query"],
            "per-page": NPL_RESULTS_PER_QUERY,
            "select": ("id,doi,title,publication_year,publication_date,type,authorships,primary_location,best_oa_location,open_access,abstract_inverted_index,ids"),
        }

        api_key = os.getenv("OPENALEX_API_KEY", "").strip()

        if api_key:
            params["api_key"] = api_key

        url = "https://api.openalex.org/works?" + urlencode(params)

        payload = _get_json(url)

        results = []

        for work in payload.get("results") or []:
            normalized = _normalize_openalex_work(work, plan_item)

            if normalized:
                results.append(normalized)

        return {
            "provider": "OpenAlex",
            "category": plan_item["category"],
            "results": results,
            "count": len(results),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "error": None,
        }

    except Exception as exc:
        # A provider failure must not prevent the other provider from running.
        return _provider_error(
            "OpenAlex",
            plan_item["category"],
            started,
            exc,
        )


# ---------------------------------------------------------------------------
# Crossref
# ---------------------------------------------------------------------------


def _crossref_date(work: dict[str, Any]) -> str | None:
    """Extract the best available publication date from Crossref."""

    for key in (
        "published-print",
        "published-online",
        "published",
        "created",
    ):
        date_parts = (work.get(key) or {}).get("date-parts") or []

        if not date_parts or not date_parts[0]:
            continue

        parts = date_parts[0]

        if len(parts) >= 3:
            return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"

        if len(parts) == 2:
            return f"{parts[0]:04d}-{parts[1]:02d}"

        return str(parts[0])

    return None


def _normalize_crossref_work(
    work: dict[str, Any],
    plan_item: dict[str, Any],
) -> dict[str, Any] | None:

    titles = work.get("title") or []
    title = str(titles[0]).strip() if titles else ""

    if not title:
        return None

    authors = []

    for author in work.get("author") or []:
        name = " ".join(
            part
            for part in (
                author.get("given"),
                author.get("family"),
            )
            if part
        )

        if name:
            authors.append(name)

    doi_value = work.get("DOI")
    doi_url = f"https://doi.org/{doi_value}" if doi_value else None
    containers = work.get("container-title") or []

    return {
        "title": title,
        "authors": authors,
        "publication_date": _crossref_date(work),
        "document_type": work.get("type"),
        "abstract": _strip_html(work.get("abstract")),
        "doi": doi_url,
        "url": work.get("URL") or doi_url,
        "venue": containers[0] if containers else None,
        "source_provider": "Crossref",
        "provider_record_id": doi_value,
        "open_access_url": None,
        "searched_feature_ids": list(plan_item["feature_ids"]),
        "search_category": plan_item["category"],
    }


def _search_crossref(
    plan_item: dict[str, Any],
) -> dict[str, Any]:

    global _CROSSREF_LAST_REQUEST_AT

    started = time.monotonic()

    try:
        params = {
            "query.bibliographic": plan_item["query"],
            "rows": NPL_RESULTS_PER_QUERY,
            "select": ("DOI,title,author,published,published-print,published-online,created,type,URL,abstract,container-title"),
        }

        mailto = os.getenv("CROSSREF_MAILTO", "").strip()

        if mailto:
            params["mailto"] = mailto

        url = "https://api.crossref.org/works?" + urlencode(params)

        # Keep Crossref requests serial and conservatively paced.
        with _CROSSREF_REQUEST_LOCK:
            minimum_interval = 0.35 if mailto else 1.1
            elapsed = time.monotonic() - _CROSSREF_LAST_REQUEST_AT

            if _CROSSREF_LAST_REQUEST_AT and elapsed < minimum_interval:
                time.sleep(minimum_interval - elapsed)

            payload = _get_json(url)
            _CROSSREF_LAST_REQUEST_AT = time.monotonic()

        message = payload.get("message") or {}
        results = []

        for work in message.get("items") or []:
            normalized = _normalize_crossref_work(work, plan_item)

            if normalized:
                results.append(normalized)

        return {
            "provider": "Crossref",
            "category": plan_item["category"],
            "results": results,
            "count": len(results),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "error": None,
        }

    except Exception as exc:
        return _provider_error(
            "Crossref",
            plan_item["category"],
            started,
            exc,
        )


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def _deduplicate_results(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Deduplicate by DOI first, then normalized title and first author.

    Preserve source providers, source URLs, feature IDs and categories.
    """

    unique_results = []
    result_index_by_key = {}

    for result in results:
        doi = _normalize_doi(result.get("doi"))
        title = _normalize_title(result.get("title"))

        authors = result.get("authors") or []
        first_author = _normalize_title(authors[0]) if authors else ""

        if doi:
            key = f"doi:{doi}"
        elif title:
            key = f"title-author:{title}|{first_author}"
        else:
            key = ""

        # Retain records with insufficient information to deduplicate.
        if not key:
            unique_results.append(result)
            continue

        existing_index = result_index_by_key.get(key)

        if existing_index is None:
            merged = dict(result)

            merged["source_providers"] = [result["source_provider"]] if result.get("source_provider") else []
            merged["source_urls"] = [result["url"]] if result.get("url") else []
            merged["search_categories"] = [result["search_category"]] if result.get("search_category") else []
            merged["searched_feature_ids"] = list(dict.fromkeys(result.get("searched_feature_ids") or []))

            result_index_by_key[key] = len(unique_results)
            unique_results.append(merged)
            continue

        existing = unique_results[existing_index]

        for field, value in (
            ("source_providers", result.get("source_provider")),
            ("source_urls", result.get("url")),
            ("search_categories", result.get("search_category")),
        ):
            if value:
                values = existing.setdefault(field, [])

                if value not in values:
                    values.append(value)

        feature_ids = existing.setdefault("searched_feature_ids", [])

        for feature_id in result.get("searched_feature_ids") or []:
            if feature_id and feature_id not in feature_ids:
                feature_ids.append(feature_id)

        # Fill missing metadata without overwriting existing values.
        for field in (
            "abstract",
            "publication_date",
            "venue",
            "open_access_url",
            "doi",
        ):
            if not existing.get(field) and result.get(field):
                existing[field] = result[field]

    return unique_results


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------


def search_npl_openalex_crossref(
    state: PatentState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """
    Search OpenAlex and Crossref for non-patent literature.

    Returns NPL query details, normalized references and a search summary.
    """

    invention = state.get("invention")

    if invention is None:
        raise ValueError("Missing 'invention' in PatentState. Run decompose_invention before NPL search.")

    plan = _build_search_plan(invention)

    if not plan:
        return {
            "npl_queries": [],
            "npl_results": [],
            "npl_search_summary": {
                "status": "no_features",
                "query_count": 0,
                "provider_request_count": 0,
                "raw_result_count": 0,
                "deduplicated_count": 0,
                "duplicates_removed": 0,
                "provider_calls": [],
            },
        }

    raw_results = []
    provider_calls = []
    futures = []

    # At most three queries per provider, six provider requests total.
    with ThreadPoolExecutor(max_workers=min(6, len(plan) * 2)) as executor:
        for plan_item in plan:
            futures.append(executor.submit(_search_openalex, plan_item))
            futures.append(executor.submit(_search_crossref, plan_item))

        for future in as_completed(futures):
            outcome = future.result()

            provider_calls.append(
                {
                    key: outcome[key]
                    for key in (
                        "provider",
                        "category",
                        "count",
                        "elapsed_seconds",
                        "error",
                    )
                }
            )

            raw_results.extend(outcome["results"])

    unique_results = _deduplicate_results(raw_results)

    unique_results.sort(
        key=lambda item: (
            not bool(item.get("doi")),
            (item.get("title") or "").casefold(),
        )
    )

    provider_calls.sort(key=lambda item: (item["provider"], item["category"]))

    successful_calls = [call for call in provider_calls if call["error"] is None]

    if raw_results:
        status = "success"
    elif successful_calls:
        status = "no_results"
    else:
        status = "provider_error"

    summary = {
        "status": status,
        "query_count": len(plan),
        "provider_request_count": len(futures),
        "raw_result_count": len(raw_results),
        "deduplicated_count": len(unique_results),
        "duplicates_removed": len(raw_results) - len(unique_results),
        "provider_calls": provider_calls,
    }

    # Use the existing ApplicationContext audit service when available.
    configurable = (config or {}).get("configurable", {})
    context = configurable.get("context")
    thread_id = configurable.get("thread_id")
    audit = getattr(context, "audit", None) if context else None

    if audit is not None:
        try:
            audit.log_model_call(
                thread_id,
                "search_npl_openalex_crossref",
                f"NPL discovery across {len(plan)} feature categories",
                summary,
            )
        except Exception as exc:
            # Audit failure must not discard the literature results.
            print(f"NPL audit logging failed: {exc}")

    print(f"NPL search completed: status={status}, raw={len(raw_results)}, unique={len(unique_results)}, duplicates_removed={summary['duplicates_removed']}")

    for call in provider_calls:
        print(f"{call['provider']} / {call['category']}: {call['count']} results; elapsed={call['elapsed_seconds']}s; error={call['error']}")

    return {
        "npl_queries": plan,
        "npl_results": unique_results,
        "npl_search_summary": summary,
    }
