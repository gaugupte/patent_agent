

I agree. For your patent-practice product, we should prioritize free, reliable sources first, then introduce paid or licensed sources only when they add meaningful coverage that the free sources cannot provide.

I'll order the phases by cost first, then usefulness for prior-art research, while keeping IEEE and standards firmly in the plan.

## NPL sources: phased implementation plan

| Phase    | Source                    | Purpose                                               | API / access cost                                               | Decision                           |
| -------- | ------------------------- | ----------------------------------------------------- | --------------------------------------------------------------- | ---------------------------------- |
| 1A       | OpenAlex                  | Broad academic-paper discovery                        | Free daily allowance; paid for higher usage                     | Implement first                    |
| 1A       | Crossref                  | Publication metadata, DOI and date verification       | Free public API                                                 | Implement first                    |
| 1A       | arXiv                     | AI, computer science, physics and technical preprints | Free API                                                        | Implement first                    |
| 1A       | IETF                      | Internet protocols and RFCs                           | Free public API/documents                                       | Implement first                    |
| 1A       | W3C                       | Web standards and specifications                      | Free public API/documents                                       | Implement first                    |
| 1A       | 3GPP                      | Telecom standards and specifications                  | Public document access                                          | Implement first                    |
| 1B       | Semantic Scholar          | Additional academic discovery and relevance           | Free API subject to limits                                      | Add next                           |
| 1B       | PubMed / NCBI             | Biomedical and medical literature                     | Free API; rate limits apply                                     | Add when relevant                  |
| 1B       | Brave Search API          | Broader technical web search                          | Free monthly credits, then paid                                 | Trial early; monitor usage         |
| 2        | IEEE Xplore               | Engineering papers and IEEE standards                 | API access and commercial licensing must be confirmed           | High-priority licensed integration |
| 2        | ACM Digital Library       | Software and computer science research                | Access depends on service and licensing                         | Add if needed                      |
| 3        | ISO                       | International standards                               | Member/access arrangements and licensing                        | Later                              |
| 3        | IEC                       | Electrical and electronic standards                   | Access arrangements and licensing                               | Later                              |
| 3        | ASTM                      | Materials, manufacturing and testing standards        | Licensed standards access                                       | Later                              |
| Excluded | Google Scholar automation | Broad academic search                                 | No supported general-purpose public search API for our use case | Don't automate directly            |
| Excluded | Unrestricted web crawling | Crawl the entire Internet                             | High operational, cost and compliance complexity                | Don't implement                    |

## How I'd implement this without making the graph complicated

## 1

Phase 1A — Free core

OpenAlex, Crossref, arXiv and public IETF/W3C/3GPP resources. Build the shared search, normalization and deduplication pipeline.

## 2

Phase 1B — Extend coverage

Add Semantic Scholar, conditional PubMed, and a web-search API using its free allowance. Measure latency, quotas and result quality.

## 3

Phase 2 — Paid-access sources

Investigate IEEE Xplore and ACM based on the gaps found in actual search results and the commercial licensing terms.

## 4

Phase 3 — Licensed standards

Add ISO, IEC and ASTM access if the expected client value justifies the cost.

One practical qualification: free APIs don't guarantee full-text access, unrestricted commercial reuse, or unlimited requests. We'll check the current terms before implementing each provider.

My recommendation is to start with Phase 1A and one web-search provider on a free allowance, then expand only when we see a genuine coverage gap. This keeps initial costs low without closing the door on professional-grade NPL searching later.

One important distinction: a free API does not necessarily provide free access to full-text papers or standards, and API access for commercial use can have separate licensing conditions.

## 1. Academic and scientific literature

| Source           | Purpose in our patent search                                                       | API / cost status                                                                   | Decision                 |
| ---------------- | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------ |
| OpenAlex         | Discover scholarly papers, conference proceedings, authors and abstracts           | Free API allowance; paid usage beyond the allowance                                 | Phase 1                  |
| Semantic Scholar | Find relevant scientific papers, including those using different terminology       | API available with rate limits; generally free access subject to limits and terms   | Phase 2                  |
| Crossref         | Find publications and verify titles, authors, DOI and publication dates            | Public API is free; premium Metadata Plus offers higher limits and priority support | Phase 2                  |
| arXiv            | Discover preprints in AI, computer science, physics and related engineering fields | Free API                                                                            | Phase 2                  |
| PubMed / NCBI    | Find biomedical, medical and life-sciences literature                              | Free API, subject to request limits                                                 | Conditional              |
| Google Scholar   | Broad academic-paper discovery                                                     | No supported general-purpose public search API for our intended workflow            | Do not automate directly |

OpenAlex is a good first provider because it has a free daily API allowance and supports structured scholarly searches. Crossref's public API is also free, while its premium service is optional.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://help.openalex.org\&sz=32)

OpenAlex Help Center

+2



## 2. Engineering literature and standards

| Source              | Purpose in our patent search                                                        | API / cost status                                                                                               | Decision               |
| ------------------- | ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ---------------------- |
| IEEE Xplore         | Engineering papers, electronics, sensors, communications, and IEEE standards        | API access requires approval and applicable licensing; commercial use must be explicitly authorized             | Phase 2, high priority |
| ACM Digital Library | Computing, software engineering, algorithms and computer science                    | Programmatic access and reuse depend on the available service and licensing; don't assume a free commercial API | Phase 2                |
| 3GPP                | Telecom protocols and technical specifications, including historical releases       | Public specifications are available without a paid search API being necessary                                   | Phase 1                |
| IETF                | Internet protocols, RFCs and networking specifications                              | Public technical documents; direct retrieval/search can be implemented without a paid API                       | Phase 1                |
| W3C                 | Web technologies, browser standards, accessibility and web protocols                | Public standards and specifications; no paid API is necessary for basic discovery                               | Phase 1                |
| ISO                 | International standards across engineering, manufacturing, quality and other fields | API access is tied to member arrangements and licensing; standards themselves may require purchase              | Phase 3                |
| IEC                 | Electrical and electronic standards                                                 | API access is restricted to authorized members/partners; companies may request limited metadata access          | Phase 3                |
| ASTM International  | Materials, testing, manufacturing and engineering standards                         | Standards and publications are copyrighted; access and reuse may require licensing                              | Phase 3                |

IEEE's official API terms are especially important here: we should not use its API for our commercial patent product unless the required authorization is in place. Public availability of a standard or paper also doesn't automatically grant permission to store, process or redistribute it.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://developer.ieee.org\&sz=32)

IEEE Xplore® API TERMS OF USE

+3



## 3. General technical literature and web search

| Source / method                             | Purpose                                                                                                          | API / cost status                                                                     | Decision                         |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | -------------------------------- |
| Targeted web search                         | Find technical manuals, datasheets, application notes, white papers, product documentation and technical reports | Depends on the search provider; typically rate-limited or paid beyond free allowances | Phase 1                          |
| Manufacturer websites                       | Product specifications, manuals, datasheets and application notes                                                | Usually no common API; public pages can be retrieved subject to site terms            | Phase 1, through targeted search |
| Government / university repositories        | Technical reports, theses and institutional research                                                             | Varies by repository; many documents are publicly available                           | Phase 1, through targeted search |
| Technical blogs and developer documentation | Implementation details and technical disclosures                                                                 | Usually no common API; access depends on the site                                     | Phase 1, through targeted search |
| Unrestricted Internet crawling              | Crawl arbitrary websites at scale                                                                                | Expensive and operationally complex; access and reuse restrictions vary               | Do not implement                 |
| Direct automated Google Scholar search      | Broad scholarly discovery                                                                                        | No supported general-purpose public search API for this workflow                      | Do not implement                 |

For web search, one possible API is Brave Search, which currently advertises $5 in monthly credits and then charges per request. Google's Custom Search JSON API is closed to new customers, so I would not build a new integration around it.&#x20;

[image](https://www.google.com/s2/favicons?domain=https://brave.com\&sz=32)

Brave

+1



## 4. Consolidated implementation decision

Here is the complete source list with our agreed priorities.

| Source                   | Purpose                                     | Free / paid                                | Final decision                  |
| ------------------------ | ------------------------------------------- | ------------------------------------------ | ------------------------------- |
| OpenAlex                 | Academic discovery                          | Free allowance; paid at higher usage       | Phase 1                         |
| Targeted web search      | Technical documents and broader disclosures | Provider-dependent; potentially paid       | Phase 1                         |
| Semantic Scholar         | Academic and semantic paper discovery       | Free API subject to limits                 | Phase 2                         |
| Crossref                 | Publication metadata and DOI verification   | Free public API; paid premium option       | Phase 2                         |
| arXiv                    | Scientific preprints                        | Free API                                   | Phase 2                         |
| 3GPP                     | Telecom specifications                      | Public/free document access                | Phase 1                         |
| IETF                     | Networking standards and RFCs               | Public/free document access                | Phase 1                         |
| W3C                      | Web standards                               | Public/free document access                | Phase 1                         |
| IEEE Xplore              | Engineering papers and IEEE standards       | API access/licensing must be approved      | Phase 2 — high priority         |
| ACM Digital Library      | Software and computing literature           | Access and licensing dependent             | Phase 2                         |
| PubMed / NCBI            | Biomedical research                         | Free API                                   | Conditional                     |
| ISO                      | International standards                     | Member/licensing arrangements              | Phase 3                         |
| IEC                      | Electrical/electronic standards             | Restricted API access; licensing may apply | Phase 3                         |
| ASTM                     | Materials and testing standards             | Copyrighted; licensing may apply           | Phase 3                         |
| Google Scholar           | Academic discovery                          | No suitable supported public search API    | Excluded from direct automation |
| Unrestricted web crawler | General Internet collection                 | High operational and compliance complexity | Excluded                        |

“Phase 1” here means the agreed initial source scope; it does not mean every source needs its own API integration. The implementation can use one shared search mechanism for web discovery and direct retrieval for public standards repositories.

### My recommendation before we code

For the first working implementation, I would keep the actual API integrations to just:

1. OpenAlex — structured academic search.
2. One web-search provider — broad technical-document discovery.

We'll design the provider interface so that 3GPP, IETF, W3C and IEEE can be added without changing the core LangGraph workflow. We can decide whether direct standards retrieval should be enabled in the first release based on the invention's domain.

That is the smallest implementation that lets us test execution time, result quality and feature mapping before investing in more integrations.



Yes — **if we implement all of Phase 1 as separate integrations, it can become a project in itself.** And I don't think we should do that right now.

I would simplify the first implementation substantially:

### Phase 1A — build the NPL capability, not eight integrations

| Component | What we actually build now |
|---|---|
| **1. NPL query generator** | One node using your existing structural/procedural/functional features |
| **2. Web search** | One provider for broad technical literature/document discovery |
| **3. OpenAlex** | One structured academic source |
| **4. Result normalization** | Convert everything into one `NPLReference` model |
| **5. Deduplication** | DOI/title/URL based |
| **6. Relevance analysis** | Map each result back to your invention features |
| **7. Report** | Add the NPL section to your existing report |

That's it.

We **don't need separate nodes for OpenAlex, Crossref, Semantic Scholar, arXiv, 3GPP, IETF, W3C, etc.**

Instead, I'd make the architecture:

```text
generate_npl_queries
        │
        ├── OpenAlex
        │
        └── Web Search
              │
              ▼
        normalize results
              │
              ▼
          deduplicate
              │
              ▼
       relevance analysis
              │
              ▼
        NPL report section
```

Then later, adding IEEE becomes simply another provider:

```text
                ┌── OpenAlex
NPL queries ────┼── Web
                ├── IEEE       ← later
                ├── Semantic Scholar
                ├── 3GPP
                └── PubMed
```

### Why I prefer this for your project

You already have a fairly substantial LangGraph workflow — decomposition → keywords → CPC → USPTO queries → Espacenet queries → report.

I **don't want NPL to become another giant subsystem before we've proven that it adds value**.
So I'd suggest we first get this working end-to-end:

> **IDF → features → NPL queries → 10–20 useful NPL references → feature mapping → report**

Once that works well, we can add providers one at a time.

That should turn this from a potentially **weeks-long integration exercise into a relatively contained next step**.

And I think **OpenAlex + targeted web search is enough for our first working NPL version**. IEEE/standards can come immediately afterward once we know exactly what gaps we're seeing.