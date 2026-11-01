# Multi-source asynchronous NPL discovery integration
# https://www.google.com/search?sourceid=chrome&ie=UTF-8&amc=1&gs_lcrp=EgZjaHJvbWUqFQgFEAAYQhi0AhjqAhjwBRieBhj2BjISCAAQIxgnGOoCGPAFGJ4GGKIHMhIIARAjGCcY6gIY8AUYngYYogcyEggCECMYJxjqAhjwBRieBhiiBzISCAMQIxgnGOoCGPAFGJ4GGKIHMhIIBBAjGCcY6gIY8AUYngYYogcyFQgFEAAYQhi0AhjqAhjwBRieBhj2BtIBDjU1NzA3MjE0MmowajMzqAIGsAIB&oq=&udm=50&cud=0&sxsrf=APpeQnse5OgFdTXKggU3Pr-d1EbvV-3iLA%3A1793111187797&mstk=AUtExfDrFjMubBDMRxqk-ZMj_TG6-3r-kwysDHc3S3s2o-klD3pwbPOBagYdYeB9OdPTq9UBSTNrDbouUS680PxRk_OQJUTlqzXD8s9a3s5GR_okODECmPEM6a3Rz6S6ST_8XSXD1F0VIOjS1JHQ-BzR-fXEdH9k6fB667mZhYURxPbcQb-5wZX7VsYIEFEPFW10QTCaCTZs76ge-Uf8VxtUvgb2-NlBKmk92Qhf6L1wW7MQeC2yWAt3FB57ChIHCVnjzNDcD2uFfLoeUQyIc3QHqic55aM0mP6LhUjBQXvr4NooLt4kLFEXwEG8qMgFCl58ImkeR-s9V-738w&mtid=jNzMatq4NuKVseMPwvKdmQw&csuir=1&aep=26&q=doi+in+research+paper&ved=0CAEQ2_wOahgKEwjggJjcs9qXAxUAAAAAHQAAAAAQrws


## Files
- `graph/npl_search.py`: async `httpx` node querying Semantic Scholar, OpenAlex, OpenAIRE, and arXiv concurrently, with optional SerpApi Google Scholar search; normalizes/deduplicates results and LLM-reranks up to 50 candidates.
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
$env:SERPAPI_API_KEY = "YOUR_KEY"
$env:ENABLE_SERPAPI_GOOGLE_SCHOLAR = "true"
```
Semantic Scholar's API key is optional but recommended to reduce rate-limit problems. OpenAlex can be tried without a key. OpenAIRE Graph and arXiv APIs do not require a key.
Google Scholar through SerpApi is disabled by default. Set both SerpApi variables above to enable one search per feature category (up to three searches per analysis). The free plan is limited to 250 searches per month. Keep this source for internal evaluation: SerpApi's terms restrict reselling or exploiting its service without written permission, and its U.S. Legal Shield is not included on the free plan. Confirm current provider terms before expanding use.

## Integration
Copy the files into the corresponding locations in the existing project, preserving any project-specific changes in `config/state.py` and `graph/graph_builder.py`. The node uses `configurable.context.llm` and calls `llm.ainvoke(...)` for query planning and reranking. If the LLM isn't available or a call fails, it falls back to deterministic queries / lexical ranking and records that in the summary.

The graph node is async. LangGraph supports async nodes; invoke the graph asynchronously (for example, `await graph.ainvoke(...)`) when running an async application.

## Important interpretation limits
- Semantic Scholar's ordinary paper-search endpoint accepts plain-text queries, not user-supplied embedding vectors.
- OpenAlex `works?search=` is text search; the code retains returned topics/keywords for review rather than claiming this is a vector-similarity call.
- arXiv `published` is recorded as the feed's submission/publication timestamp and `updated` is recorded separately. Confirm original public availability and version history before relying on a date in legal analysis.
- LLM scores are triage aids, not legal novelty, inventive-step, or patentability conclusions. The human reviewer must inspect original sources.
- The node does not download or analyze full texts.


//#==============================================================================================================================================


To make sense of this "alphabet soup," it helps to organize these names into four distinct categories: Search Engines, Global Metadata Catalogs, Repositories/Publishers, and Standards Organizations.

Category 1: The Public Search Engines (How you find papers)

These platforms crawl the web or ingest huge datasets to provide a searchable interface for researchers to discover papers.
• Google Scholar: The largest, most massive search engine for academic literature. It uses automated bots to crawl everything from open websites to university pages. It is unparalleled in size but operates like a "black box"—it doesn't share its raw data, and its data quality can be messy. 
[1] (https://libraries.uvm.edu/c.php?g=1499226&p=11246855), [2] (https://casrai.org/guides/metadata-search-engines-for-scholarly-research), [3] (https://scipubplus.com/hub/blog/multidisciplinary-research-databases-guide/)

• Semantic Scholar: An AI-powered search engine created by the Allen Institute for AI. It is highly popular in Computer Science and Tech. Its standout features are AI-driven summaries ("TLDRs") and an automated system that analyzes how papers cite each other (e.g., separating casual citations from papers that actually build on the research). [1] (https://intuitionlabs.ai/articles/openalex-semantic-scholar-pubmed-comparison), [2] (https://openscience.eu/article/infrastructure/open-research-platforms-part-1), [3] (https://intuitionlabs.ai/articles/openalex-semantic-scholar-pubmed-comparison), [4] (https://casrai.org/guides/metadata-search-engines-for-scholarly-research)

Category 2: The Infrastructure & Metadata Catalogs (The database behind the scenes)

These are not meant for general reading. They act as massive "phone books" or knowledge graphs connecting papers, authors, and institutions. [1] (https://ijcrt.org/blog_ijcrt/ijcrt_blog_blog26.html)

• Crossref: A DOI registry. When a publisher wants to create a DOI for a paper, they upload the paper's basic information (title, authors, publication date) to Crossref. It is the official, authoritative backbone of academic metadata. [1] (https://pmc.ncbi.nlm.nih.gov/articles/PMC13157964/)
• OpenAlex: A massive, 100% free and open-source data graph of the world's research (named after the Library of Alexandria). It takes metadata from Crossref, arXiv, and other places, unifies them, and lets data-driven researchers download or query the entire global database for free. [1] (https://openalex.org/), [2] (https://arxiv.org/html/2512.16434v1), [3] (https://ijcrt.org/blog_ijcrt/ijcrt_blog_blog26.html), [4] (https://intuitionlabs.ai/articles/openalex-semantic-scholar-pubmed-comparison), [5] (https://scipubplus.com/hub/blog/multidisciplinary-research-databases-guide/)

Category 3: Repositories & Publishers (Where the papers actually live)

These organizations host the actual text of the articles.
• arXiv (pronounced "archive"): A highly famous preprint repository. Scientists (mostly in Physics, Math, and Computer Science) upload their papers here before they are peer-reviewed or published in journals so the community can read them for free immediately.
• IEEE Xplore: A digital library and publisher run by the Institute of Electrical and Electronics Engineers. It hosts peer-reviewed journals, conference proceedings, and standards explicitly focused on electrical engineering, computer science, and electronics. (Unlike arXiv, much of it sits behind a paid subscription). [1] (https://papersflow.ai/blog/academic-research-databases-complete-list), [2] (https://intuitionlabs.ai/articles/openalex-semantic-scholar-pubmed-comparison)

Category 4: The Standards Organizations (Not research papers, but industry rules)

These do not publish academic studies. They create technical standards—the specific rules, guidelines, and blueprints that industries must follow to ensure safety and compatibility worldwide.
• ISO (International Organization for Standardization): A global body that develops international standards for almost everything—from data security (ISO 27001) to manufacturing quality.
• IEC (International Electrotechnical Commission): A global organization that specifically creates standards for all electrical, electronic, and related technologies (often partnering with ISO).
• ASTM (American Society for Testing and Materials): A standards organization that develops technical specifications specifically for materials, products, systems, and services (like the exact steel grade needed for a bridge or safety rules for consumer goods).

🔍 Direct Comparison at a Glance


Name	                What is it?	                Main Purpose
Google Scholar	        Search Engine	        Broadest, fastest way to search for any paper.
Semantic Scholar	    AI Search Engine	    Finding papers using AI summaries and citation mapping.
Crossref	            DOI Registry	        The background infrastructure providing paper metadata.
OpenAlex	            Open Data Graph	        Analyzing global scientific output using open data sets.
arXiv	                Preprint Repository	    Sharing un-reviewed math/tech papers for free.
IEEE Xplore	            Publisher Library	    Accessing top-tier engineering & tech articles.
ISO / IEC / ASTM	    Standards Bodies	    Providing structural blueprints and rules for global industries.

Are you trying to find specific papers for a literature review, or are you looking to download large amounts of citation data for an analysis? Let me know, and I can point you toward the exact tool for the job.
