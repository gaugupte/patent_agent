from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from lxml import etree

from models.cpc_models import CPCRecord


# =============================================================================
# CPC CODE PATTERNS
# =============================================================================

CPC_SECTION_RE = re.compile(r"^[A-HY]$")
CPC_CLASS_RE = re.compile(r"^[A-HY]\d{2}$")
CPC_SUBCLASS_RE = re.compile(r"^[A-HY]\d{2}[A-Z]$")
CPC_MAIN_GROUP_RE = re.compile(r"^[A-HY]\d{2}[A-Z]\d{1,4}/00$")
CPC_SUBGROUP_RE = re.compile(r"^[A-HY]\d{2}[A-Z]\d{1,4}/(?!00$)\d{2,6}$")

# CPC references appearing in title/reference text.
CPC_REFERENCE_RE = re.compile(r"\b[A-HY]\d{2}[A-Z]\d{1,4}/\d{2,6}\b")

CPC_SHORT_REFERENCE_RE = re.compile(r"\b[A-HY]\d{2}[A-Z]\d{1,4}\b")


# =============================================================================
# VALIDATION RESULT
# =============================================================================


@dataclass
class CPCValidationResult:
    """
    Validation result expected by cpc_ingest.py.
    """

    total_records: int = 0

    empty_titles: list[str] = field(default_factory=list)

    invalid_codes: list[str] = field(default_factory=list)

    suspicious_titles: list[str] = field(default_factory=list)

    broken_hierarchies: list[dict] = field(default_factory=list)

    missing_parents: list[tuple[str, str]] = field(default_factory=list)

    duplicate_ancestors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not (
            self.empty_titles
            or self.invalid_codes
            or self.suspicious_titles
            or self.broken_hierarchies
            or self.duplicate_ancestors
        )


# =============================================================================
# XML HELPERS
# =============================================================================


def local_name(tag: str) -> str:
    """
    Return XML local name without namespace.
    """

    if "}" in tag:
        return tag.rsplit("}", 1)[1]

    return tag


def clean_text(text: str | None) -> str:
    """
    Normalize whitespace.
    """

    if not text:
        return ""

    text = re.sub(r"\s+", " ", text)

    return text.strip(" ;,\n\t")


def direct_children(
    element,
    name: str,
):
    for child in element:
        if local_name(child.tag) == name:
            yield child


def first_direct_child(
    element,
    name: str,
):
    for child in direct_children(element, name):
        return child

    return None


def iter_non_classification_descendants(
    element,
):
    """
    Traverse descendants but NEVER enter a nested classification-item.

    This prevents child CPC titles from being included in a parent's title.
    """

    for child in element:
        if local_name(child.tag) == "classification-item":
            continue

        yield child

        yield from iter_non_classification_descendants(child)


def first_non_nested_descendant(
    element,
    name: str,
):
    for node in iter_non_classification_descendants(element):
        if local_name(node.tag) == name:
            return node

    return None


# =============================================================================
# CPC CODE FUNCTIONS
# =============================================================================


def normalize_code(
    code: str | None,
) -> str:

    if not code:
        return ""

    code = clean_text(code)

    code = re.sub(
        r"\s*/\s*",
        "/",
        code,
    )

    return code.upper()


def is_valid_cpc_code(
    code: str,
) -> bool:

    if not code:
        return False

    return bool(
        CPC_SECTION_RE.match(code)
        or CPC_CLASS_RE.match(code)
        or CPC_SUBCLASS_RE.match(code)
        or CPC_MAIN_GROUP_RE.match(code)
        or CPC_SUBGROUP_RE.match(code)
    )


def cpc_level(
    code: str,
) -> int | None:

    if CPC_SECTION_RE.match(code):
        return 3

    if CPC_CLASS_RE.match(code):
        return 4

    if CPC_SUBCLASS_RE.match(code):
        return 5

    if CPC_MAIN_GROUP_RE.match(code):
        return 7

    if CPC_SUBGROUP_RE.match(code):
        return 8

    return None


# =============================================================================
# CPC STRUCTURAL PARENT
# =============================================================================


def derive_structural_parent(
    code: str,
) -> str | None:
    """
    Determine structural CPC parent.

    Examples:

        A                  -> None
        A01                -> A
        A01B               -> A01
        A01B1/00           -> A01B
        A01B1/02           -> A01B1/00

        A47G19/00          -> A47G
        A47G19/22          -> A47G19/00

        G01F23/00          -> G01F
        G01F25/20          -> G01F25/00
    """

    code = normalize_code(code)

    if not code:
        return None

    # Section
    if CPC_SECTION_RE.match(code):
        return None

    # Class -> Section
    if CPC_CLASS_RE.match(code):
        return code[0]

    # Subclass -> Class
    if CPC_SUBCLASS_RE.match(code):
        return code[:3]

    # Main group -> Subclass
    if CPC_MAIN_GROUP_RE.match(code):
        left, _ = code.split("/", 1)

        return left[:4]

    # Subgroup -> Main group
    if CPC_SUBGROUP_RE.match(code):
        left, _ = code.split("/", 1)

        return f"{left}/00"

    return None


def build_structural_chain(
    code: str,
) -> list[str]:
    """
    Example:

        A47G19/22

    becomes:

        A
        A47
        A47G
        A47G19/00
        A47G19/22
    """

    code = normalize_code(code)

    if not code:
        return []

    chain = []

    current = code

    while current:
        chain.append(current)

        current = derive_structural_parent(current)

    chain.reverse()

    return chain


# =============================================================================
# TITLE / REFERENCE EXTRACTION
# =============================================================================


def _node_text_excluding_references(
    element,
) -> str:
    """
    Extract text from an XML subtree while excluding reference-like
    elements.

    This is useful where the CPC XML explicitly represents cross
    references as child XML nodes.
    """

    pieces = []

    ignored = {
        "reference",
        "classification-reference",
        "classification-symbol",
        "classification-item",
    }

    def walk(node):

        if local_name(node.tag) in ignored:
            return

        if node.text:
            pieces.append(node.text)

        for child in node:
            if local_name(child.tag) in ignored:
                continue

            walk(child)

            if child.tail:
                pieces.append(child.tail)

    walk(element)

    return clean_text(" ".join(pieces))


def _strip_embedded_cpc_references(
    text: str,
) -> str:
    """
    Remove CPC classification references that have been serialized
    directly into title text.

    Examples:

        'glass or drinking-vessel underlays A47G23/03'

    becomes:

        'glass or drinking-vessel underlays'

    and:

        'cups as travelling or camp articles A45F3/16 A45F3/20'

    becomes:

        'cups as travelling or camp articles'

    """

    if not text:
        return ""

    # Remove full CPC references.
    text = CPC_REFERENCE_RE.sub(
        "",
        text,
    )

    # Remove short CPC references where present.
    text = CPC_SHORT_REFERENCE_RE.sub(
        "",
        text,
    )

    # Clean punctuation left behind by reference removal.
    text = re.sub(
        r"\s*;\s*",
        "; ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    # Remove dangling punctuation at the end.
    text = re.sub(
        r"\s+([,;:.])",
        r"\1",
        text,
    )

    text = re.sub(
        r"([,;:])\s*$",
        "",
        text,
    )

    return clean_text(text)


def _extract_title_parts(
    title_element,
) -> list[str]:
    """
    Extract title-part text while keeping reference elements separate.

    The CPC XML may contain structures such as:

        class-title
            title-part
            title-part
            reference

    We want title-part text, but not the reference material.
    """

    parts = []

    for node in title_element.iter():
        lname = local_name(node.tag)

        if lname in {
            "reference",
            "classification-reference",
            "classification-symbol",
        }:
            continue

        if lname == "title-part":
            text = _node_text_excluding_references(node)

            if text:
                parts.append(text)

    return parts


def extract_title(
    classification_item,
) -> str:
    """
    Extract ONLY the semantic title of the current classification item.

    Three layers of protection are used:

    1. Never enter nested classification-items.
    2. Exclude explicit reference XML elements.
    3. Remove CPC codes that were serialized directly into title text.
    """

    title_element = first_direct_child(
        classification_item,
        "class-title",
    )

    if title_element is None:
        title_element = first_direct_child(
            classification_item,
            "title",
        )

    if title_element is None:
        title_element = first_non_nested_descendant(
            classification_item,
            "class-title",
        )

    if title_element is None:
        title_element = first_non_nested_descendant(
            classification_item,
            "title",
        )

    if title_element is None:
        return ""

    # -------------------------------------------------------------
    # Preferred extraction: title-part elements
    # -------------------------------------------------------------

    parts = _extract_title_parts(title_element)

    if parts:
        title = " ".join(parts)

    else:
        # ---------------------------------------------------------
        # Fallback if title-part is absent.
        # ---------------------------------------------------------

        title = _node_text_excluding_references(title_element)

    # -------------------------------------------------------------
    # Remove embedded CPC references.
    # -------------------------------------------------------------

    title = _strip_embedded_cpc_references(title)

    # -------------------------------------------------------------
    # Remove obvious reference lead-ins.
    #
    # This handles cases where reference wording is retained but
    # the actual CPC code has already been stripped.
    # -------------------------------------------------------------

    title = re.sub(
        r"\s+(see|cf\.?|compare)\s*$",
        "",
        title,
        flags=re.IGNORECASE,
    )

    return clean_text(title)


# =============================================================================
# CODE EXTRACTION
# =============================================================================


def extract_code(
    classification_item,
) -> str:

    symbol = first_direct_child(
        classification_item,
        "classification-symbol",
    )

    if symbol is None:
        symbol = first_non_nested_descendant(
            classification_item,
            "classification-symbol",
        )

    if symbol is None:
        return ""

    return normalize_code("".join(symbol.itertext()))


# =============================================================================
# LEVEL EXTRACTION
# =============================================================================


def extract_level(
    classification_item,
) -> int | None:

    level_element = first_direct_child(
        classification_item,
        "classification-level",
    )

    if level_element is None:
        level_element = first_non_nested_descendant(
            classification_item,
            "classification-level",
        )

    if level_element is not None:
        text = clean_text("".join(level_element.itertext()))

        try:
            return int(text)

        except ValueError:
            pass

    return cpc_level(extract_code(classification_item))


# =============================================================================
# NOTES
# =============================================================================


def extract_notes(
    classification_item,
) -> list[str]:

    notes = []

    for node in iter_non_classification_descendants(classification_item):
        lname = local_name(node.tag)

        if lname not in {
            "note",
            "class-ref",
        }:
            continue

        text = clean_text(" ".join(node.itertext()))

        if text and text not in notes:
            notes.append(text)

    return notes


# =============================================================================
# REFERENCES
# =============================================================================


def extract_references(
    classification_item,
) -> list[str]:

    references = []

    for node in iter_non_classification_descendants(classification_item):
        lname = local_name(node.tag)

        if lname not in {
            "reference",
            "classification-reference",
        }:
            continue

        text = clean_text(" ".join(node.itertext()))

        if text and text not in references:
            references.append(text)

    return references


# =============================================================================
# CLASSIFICATION ITEMS
# =============================================================================


def iter_classification_items(
    root,
) -> Iterable:

    for element in root.iter():
        if local_name(element.tag) == "classification-item":
            yield element


# =============================================================================
# RECORD CREATION
# =============================================================================


def parse_classification_item(
    classification_item,
    source_file: str | None = None,
) -> CPCRecord | None:

    code = extract_code(classification_item)

    if not code:
        return None

    if not is_valid_cpc_code(code):
        return None

    title = extract_title(classification_item)

    level = extract_level(classification_item)

    notes = extract_notes(classification_item)

    references = extract_references(classification_item)

    hierarchy_codes = build_structural_chain(code)

    parent_code = hierarchy_codes[-2] if len(hierarchy_codes) >= 2 else None

    return CPCRecord(
        code=code,
        title=title,
        level=level,
        parent_code=parent_code,
        parent_title=None,
        ancestor_codes=hierarchy_codes[:-1],
        ancestor_titles=[],
        hierarchy_codes=hierarchy_codes,
        hierarchy_titles=[],
        notes=notes,
        references=references,
        source_file=source_file,
        source_occurrences=1,
    )


# =============================================================================
# DUPLICATE MERGING
# =============================================================================


def merge_records(
    existing: CPCRecord,
    incoming: CPCRecord,
) -> CPCRecord:

    existing.source_occurrences += incoming.source_occurrences

    # Prefer non-empty and shorter/cleaner title.
    if incoming.title:
        if not existing.title:
            existing.title = incoming.title

        elif len(incoming.title) < len(existing.title):
            existing.title = incoming.title

    existing.notes = list(dict.fromkeys(existing.notes + incoming.notes))

    existing.references = list(dict.fromkeys(existing.references + incoming.references))

    if existing.level is None:
        existing.level = incoming.level

    if existing.parent_code is None:
        existing.parent_code = incoming.parent_code

    if existing.source_file is None:
        existing.source_file = incoming.source_file

    return existing


# =============================================================================
# HIERARCHY ENRICHMENT
# =============================================================================


def enrich_hierarchy(
    records: dict[str, CPCRecord],
) -> None:
    """
    Populate parent and hierarchy titles.
    """

    for record in records.values():
        hierarchy_titles = []

        for code in record.hierarchy_codes:
            parent = records.get(code)

            if parent is None:
                hierarchy_titles.append("")

            else:
                hierarchy_titles.append(parent.title)

        record.hierarchy_titles = hierarchy_titles

        if record.parent_code:
            parent = records.get(record.parent_code)

            if parent:
                record.parent_title = parent.title

        # Remove duplicate ancestors.
        seen = set()

        clean_ancestors = []

        for code in record.ancestor_codes:
            if code not in seen:
                seen.add(code)

                clean_ancestors.append(code)

        record.ancestor_codes = clean_ancestors


# =============================================================================
# TITLE VALIDATION
# =============================================================================


def title_is_suspicious(
    title: str,
) -> bool:
    """
    Detect titles that are very likely polluted.
    """

    if not title:
        return True

    # A normal CPC heading should not be enormous.
    if len(title) > 1200:
        return True

    # Excessive separators are a strong pollution signal.
    if title.count(";") > 25:
        return True

    if title.count(":") > 15:
        return True

    # A title should not contain a large number of CPC references.
    if len(CPC_REFERENCE_RE.findall(title)) > 3:
        return True

    return False


# =============================================================================
# VALIDATION
# =============================================================================


def validate_records(
    records: dict[str, CPCRecord],
) -> CPCValidationResult:

    result = CPCValidationResult(total_records=len(records))

    for code, record in records.items():
        # -------------------------------------------------------------
        # Code validation
        # -------------------------------------------------------------

        if not is_valid_cpc_code(code):
            result.invalid_codes.append(code)

        # -------------------------------------------------------------
        # Title validation
        # -------------------------------------------------------------

        if not record.title:
            result.empty_titles.append(code)

        elif title_is_suspicious(record.title):
            result.suspicious_titles.append(code)

        # -------------------------------------------------------------
        # Hierarchy validation
        # -------------------------------------------------------------

        expected_parent = derive_structural_parent(code)

        if expected_parent != record.parent_code:
            result.broken_hierarchies.append(
                {
                    "code": code,
                    "expected": expected_parent,
                    "actual": record.parent_code,
                }
            )

        # -------------------------------------------------------------
        # Missing source parent
        # -------------------------------------------------------------

        if record.parent_code and record.parent_code not in records:
            result.missing_parents.append(
                (
                    code,
                    record.parent_code,
                )
            )

        # -------------------------------------------------------------
        # Duplicate ancestors
        # -------------------------------------------------------------

        if len(record.ancestor_codes) != len(set(record.ancestor_codes)):
            result.duplicate_ancestors.append(code)

    return result


# =============================================================================
# XML FILE PARSER
# =============================================================================


def parse_cpc_xml_file(
    xml_path: Path,
) -> list[CPCRecord]:

    parser = etree.XMLParser(
        huge_tree=True,
        recover=True,
        remove_comments=True,
    )

    with xml_path.open("rb") as f:
        tree = etree.parse(
            f,
            parser,
        )

    root = tree.getroot()

    records = []

    for classification_item in iter_classification_items(root):
        record = parse_classification_item(
            classification_item,
            source_file=xml_path.name,
        )

        if record:
            records.append(record)

    return records


# =============================================================================
# DIRECTORY PARSER
# =============================================================================


def parse_cpc_directory(
    xml_directory: str | Path,
):
    """
    Parse all CPC XML files.

    Returns exactly:

        records, validation

    to remain compatible with cpc_ingest.py.
    """

    xml_directory = Path(xml_directory)

    if not xml_directory.exists():
        raise FileNotFoundError(f"CPC XML directory does not exist: {xml_directory}")

    xml_files = sorted(p for p in xml_directory.rglob("*.xml") if p.is_file())

    if not xml_files:
        raise FileNotFoundError(f"No XML files found under: {xml_directory}")

    canonical: dict[str, CPCRecord] = {}

    print(f"Found {len(xml_files):,} XML files")

    for index, xml_file in enumerate(
        xml_files,
        start=1,
    ):
        print(f"[{index:,}/{len(xml_files):,}] Parsing {xml_file.name}")

        file_records = parse_cpc_xml_file(xml_file)

        for record in file_records:
            existing = canonical.get(record.code)

            if existing is None:
                canonical[record.code] = record

            else:
                canonical[record.code] = merge_records(
                    existing,
                    record,
                )

    # Populate hierarchy after all
    # duplicate records have been merged.
    enrich_hierarchy(canonical)

    validation = validate_records(canonical)

    return canonical, validation


# =============================================================================
# SAMPLE OUTPUT
# =============================================================================


def print_sample(
    records: dict[str, CPCRecord],
    code: str,
) -> None:

    record = records.get(code)

    print()
    print("=" * 79)
    print(code)
    print("=" * 79)

    if record is None:
        print("NOT FOUND")

        return

    print(f"TITLE: {record.title}")

    print(f"LEVEL: {record.level}")

    print(f"PARENT: {record.parent_code}")

    print(f"PARENT TITLE: {record.parent_title}")

    print("ANCESTORS: " + " | ".join(record.ancestor_codes))

    print("HIERARCHY: " + " | ".join(record.hierarchy_codes))

    print(
        "HIERARCHY TITLES: "
        + " | ".join(title if title else "[not present in XML]" for title in record.hierarchy_titles)
    )

    print(f"REFERENCES: {len(record.references)}")

    print()
    print("SEMANTIC TEXT:")

    print(record.build_semantic_text())


def print_sample_records(
    records: dict[str, CPCRecord],
    sample_codes: list[str] | None = None,
) -> None:
    """
    Compatibility function expected by cpc_ingest.py.
    """

    if sample_codes is None:
        sample_codes = [
            "A01B",
            "A01B1/00",
            "A01B1/02",
            "A47G19/22",
            "A47G19/2205",
            "G01F23/00",
            "G01F25/20",
        ]

    for code in sample_codes:
        print_sample(
            records,
            code,
        )


# =============================================================================
# VALIDATION REPORT
# =============================================================================


def print_validation_report(
    validation: CPCValidationResult,
) -> None:

    print()
    print("=" * 80)
    print("CPC VALIDATION REPORT")
    print("=" * 80)

    print(f"Total records       : {validation.total_records:,}")

    print(f"Empty titles        : {len(validation.empty_titles):,}")

    print(f"Missing parents     : {len(validation.missing_parents):,}")

    print(f"Duplicate ancestors : {len(validation.duplicate_ancestors):,}")

    print(f"Broken hierarchies  : {len(validation.broken_hierarchies):,}")

    print(f"Suspicious titles   : {len(validation.suspicious_titles):,}")

    print(f"Invalid codes       : {len(validation.invalid_codes):,}")

    print()

    print("VALIDATION STATUS: " + ("PASS" if validation.valid else "FAIL"))


# =============================================================================
# CONVENIENCE LOADER
# =============================================================================


def load_cpc_records(
    xml_directory: str | Path,
) -> dict[str, CPCRecord]:

    records, validation = parse_cpc_directory(xml_directory)

    print_validation_report(validation)

    return records
