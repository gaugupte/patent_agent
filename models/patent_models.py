from pydantic import BaseModel, Field


class StructuralFeature(BaseModel):
    feature_id: str = Field(description="Unique identifier such as SF-01")
    feature: str = Field(description="A concrete structural component or element of the invention")
    details: str = Field(description="Important technical details about the structural feature")


class ProceduralFeature(BaseModel):
    feature_id: str = Field(description="Unique identifier such as PF-01")
    step: str = Field(description="A process or operational step performed by the invention")
    details: str = Field(description="Important technical details about how the step is performed")


class FunctionalFeature(BaseModel):
    feature_id: str = Field(description="Unique identifier such as FF-01")
    function: str = Field(description="A function or capability provided by the invention")
    details: str = Field(description="Important technical details about how the function is achieved")


class InventionRepresentation(BaseModel):
    invention_summary: str = Field(description="Concise technical summary of the invention")
    structural_features: list[StructuralFeature] = Field(
        description="Structural components and physical/system elements"
    )
    procedural_features: list[ProceduralFeature] = Field(
        description="Operational or process steps performed by the invention"
    )
    functional_features: list[FunctionalFeature] = Field(
        description="Functions and capabilities provided by the invention"
    )


# --- keywords


class KeywordSet(BaseModel):
    feature_id: str
    feature: str
    primary_keywords: list[str] = Field(description="Most important technical terms for this feature")
    synonyms: list[str] = Field(description="Technical synonyms and equivalent terminology")
    alternative_terms: list[str] = Field(description="Alternative terminology that may appear in patent literature")


class KeywordAnalysis(BaseModel):
    structural_keywords: list[KeywordSet]
    procedural_keywords: list[KeywordSet]
    functional_keywords: list[KeywordSet]
    consolidated_keywords: list[str]


# --- CPC analysis
class CPCCandidate(BaseModel):
    cpc_code: str
    title: str
    level: int | None = None
    relevance: str
    reason: str
    feature_id: str | None = None


class CPCAnalysis(BaseModel):
    candidates: list[CPCCandidate] = Field(
        description="Relevant CPC classifications selected from the retrieved candidates"
    )


# ******************************************************************************************************************************************


class USPTOQuery(BaseModel):
    query_name: str = Field(description="Name of the USPTO search query")

    query: str = Field(description="USPTO Patent Public Search query string")

    purpose: str = Field(description="Purpose of the search query")

    feature_ids: list[str] = Field(default_factory=list, description="Invention features targeted by this query")

    priority: str = Field(description="PRIMARY or SECONDARY")


class USPTOQueryAnalysis(BaseModel):
    queries: list[USPTOQuery] = Field(description="USPTO-ready search queries")


# ******************************************************************************************************************************************


# class EspacenetQuery(BaseModel):
#     query_name: str = Field(description="Name of the Espacenet search query")
#     query: str = Field(description="Espacenet Smart Search query string")
#     purpose: str = Field(description="Purpose of the search query")
#     feature_ids: list[str] = Field(default_factory=list, description="Invention features targeted by this query")
#     priority: str = Field(description="PRIMARY or SECONDARY")


# class EspacenetQueryAnalysis(BaseModel):
#     queries: list[EspacenetQuery] = Field(description="Espacenet-ready search queries")


class EspacenetQuery(BaseModel):
    query_name: str
    query: str
    purpose: str
    priority: str


class EspacenetQueryAnalysis(BaseModel):
    queries: list[EspacenetQuery]


# ******************************************************************************************************************************************
