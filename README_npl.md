# Three-source asynchronous NPL discovery integration

## Files
- `graph/npl_search.py`: async `httpx` node querying Semantic Scholar, OpenAlex, and arXiv concurrently; normalizes/deduplicates results and LLM-reranks up to 50 candidates.
- `graph/graph_builder.py`: adds `search_npl_three_sources` between `generate_espacenet_queries` and `create_client_report`.
- `config/state.py`: adds `npl_queries`, `npl_results`, and `npl_search_summary` to `PatentState`.

## Install
```powershell
pip install httpx
```

Optional environment variables:
```powershell
$env:SEMANTIC_SCHOLAR_API_KEY = "YOUR_KEY"
$env:OPENALEX_API_KEY = "YOUR_KEY"
```
Semantic Scholar's API key is optional but recommended to reduce rate-limit problems. OpenAlex can be tried without a key. arXiv API does not require a key.

## Integration
Copy the files into the corresponding locations in the existing project, preserving any project-specific changes in `config/state.py` and `graph/graph_builder.py`. The node uses `configurable.context.llm` and calls `llm.ainvoke(...)` for query planning and reranking. If the LLM isn't available or a call fails, it falls back to deterministic queries / lexical ranking and records that in the summary.

The graph node is async. LangGraph supports async nodes; invoke the graph asynchronously (for example, `await graph.ainvoke(...)`) when running an async application.

## Important interpretation limits
- Semantic Scholar's ordinary paper-search endpoint accepts plain-text queries, not user-supplied embedding vectors.
- OpenAlex `works?search=` is text search; the code retains returned topics/keywords for review rather than claiming this is a vector-similarity call.
- arXiv `published` is recorded as the feed's submission/publication timestamp and `updated` is recorded separately. Confirm original public availability and version history before relying on a date in legal analysis.
- LLM scores are triage aids, not legal novelty, inventive-step, or patentability conclusions. The human reviewer must inspect original sources.
- The node does not download or analyze full texts.
