from __future__ import annotations

from pydantic import BaseModel, Field


class CPCRecord(BaseModel):
    """
    Canonical representation of one CPC classification symbol.

    One CPC code must correspond to exactly one CPCRecord, even if
    the source XML contains the same symbol at multiple structural levels.
    """

    code: str

    # Clean semantic title — this is the primary retrieval text.
    title: str = ""

    # CPC hierarchy
    level: int | None = None
    parent_code: str | None = None
    parent_title: str | None = None

    ancestor_codes: list[str] = Field(default_factory=list)
    ancestor_titles: list[str] = Field(default_factory=list)

    # Complete path, including this record.
    hierarchy_codes: list[str] = Field(default_factory=list)
    hierarchy_titles: list[str] = Field(default_factory=list)

    # Classification components
    section: str | None = None
    class_code: str | None = None
    subclass_code: str | None = None
    main_group_code: str | None = None

    # Additional CPC information
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    cpc_specific_information: list[str] = Field(default_factory=list)

    # Source / status information
    source_file: str | None = None
    publication_date: str | None = None
    status: str | None = None

    # Flags found in CPC XML
    not_allocatable: bool = False
    additional_only: bool = False
    definition_exists: bool = False
    ipc_concordant: bool = False

    # Useful for validation/debugging
    source_occurrences: int = 1

    def build_semantic_text(self) -> str:
        """
        Text used for vector embedding.

        Deliberately excludes references, notes and warnings because
        those can contain unrelated CPC symbols and contaminate
        semantic retrieval.
        """

        parts: list[str] = []

        parts.append(f"CPC {self.code}")

        if self.title:
            parts.append(f"Title: {self.title}")

        if self.hierarchy_titles:
            hierarchy = " > ".join(title for title in self.hierarchy_titles if title)

            if hierarchy:
                parts.append(f"Classification hierarchy: {hierarchy}")

        if self.parent_title:
            parts.append(f"Parent classification: {self.parent_title}")

        return "\n\n".join(parts)

    def build_supporting_text(self) -> str:
        """
        Additional CPC information retained for inspection/reranking,
        but not included in the primary embedding.
        """

        parts: list[str] = []

        if self.notes:
            parts.append("Notes:\n" + "\n".join(self.notes))

        if self.warnings:
            parts.append("Warnings:\n" + "\n".join(self.warnings))

        if self.references:
            parts.append("References:\n" + "\n".join(self.references))

        if self.cpc_specific_information:
            parts.append("CPC-specific information:\n" + "\n".join(self.cpc_specific_information))

        return "\n\n".join(parts)
