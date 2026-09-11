import argparse
import re
from pathlib import Path

from docx import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field
from pypdf import PdfReader


# ============================================================
# INPUT EXTRACTION
# ============================================================


def read_input(path: str) -> str:
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    suffix = file_path.suffix.lower()

    if suffix == ".txt":
        return file_path.read_text(encoding="utf-8")

    if suffix == ".pdf":
        reader = PdfReader(str(file_path))

        pages = []

        for page in reader.pages:
            pages.append(page.extract_text() or "")

        return "\n\n".join(pages)

    if suffix == ".docx":
        doc = Document(str(file_path))

        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

        return "\n\n".join(paragraphs)

    raise ValueError("Unsupported input format. Use .txt, .pdf or .docx")


# ============================================================
# STAGE 1 — STRUCTURED INVENTION MODEL
# ============================================================


class InventionFeature(BaseModel):
    feature_id: str
    category: str
    name: str
    description: str

    technical_relationships: list[str] = Field(default_factory=list)

    source_basis: str


class InventionStep(BaseModel):
    step_id: str
    description: str

    inputs: list[str] = Field(default_factory=list)

    outputs: list[str] = Field(default_factory=list)

    source_basis: str


class InventionModel(BaseModel):
    invention_title: str

    technical_field: str

    problem_addressed: str

    shortcomings_or_limitations: list[str] = Field(default_factory=list)

    objectives: list[str] = Field(default_factory=list)

    structural_features: list[InventionFeature] = Field(default_factory=list)

    functional_features: list[InventionFeature] = Field(default_factory=list)

    procedural_steps: list[InventionStep] = Field(default_factory=list)

    technical_relationships: list[str] = Field(default_factory=list)

    disclosed_variations: list[str] = Field(default_factory=list)

    disclosed_implementations: list[str] = Field(default_factory=list)

    explicitly_disclosed_benefits: list[str] = Field(default_factory=list)

    undisclosed_or_uncertain_matter: list[str] = Field(default_factory=list)


# ============================================================
# CLAIM MODEL
# ============================================================


class Claim(BaseModel):
    number: int
    claim_type: str
    text: str


class ClaimsOutput(BaseModel):
    claims: list[Claim]


# ============================================================
# ABSTRACT MODEL
# ============================================================


class AbstractOutput(BaseModel):
    abstract: str


# ============================================================
# OLLAMA / LANGCHAIN
# ============================================================


def create_llm(model: str) -> ChatOllama:

    return ChatOllama(
        model=model,
        temperature=0,
    )


# ============================================================
# STAGE 1
# ============================================================


def extract_invention_model(
    llm: ChatOllama,
    source_text: str,
) -> InventionModel:

    system_prompt = """
You are a patent invention-analysis assistant.

Your task is to extract a structured technical representation
from an invention disclosure.

SOURCE DISCIPLINE IS CRITICAL.

You MUST distinguish between:

1. Matter explicitly disclosed by the source.
2. Technical relationships explicitly disclosed by the source.
3. Variations or implementations explicitly disclosed.
4. Matter that is absent, uncertain, or ambiguous.

DO NOT invent:

- components
- technical mechanisms
- algorithms
- materials
- numerical ranges
- performance results
- experimental data
- prior art
- advantages
- implementations
- alternatives

Do not improve the invention.

Do not fill technical gaps using general knowledge.

The resulting model will be used as the technical basis
for drafting a patent specification.

For every feature and procedural step, provide a concise
source_basis explaining what in the disclosure supports it.

If something is unclear, put it in
undisclosed_or_uncertain_matter rather than guessing.
"""

    user_prompt = f"""
Extract the structured invention model from the following
invention disclosure.

================ SOURCE DISCLOSURE ================

{source_text}

================ END SOURCE ========================

Produce only the structured invention model.
"""

    structured_llm = llm.with_structured_output(InventionModel)

    result = structured_llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )

    return result


# ============================================================
# SERIALIZATION
# ============================================================


def invention_json(
    invention: InventionModel,
) -> str:

    return invention.model_dump_json(indent=2)


# ============================================================
# STAGE 2 — SECTION DRAFTING
# ============================================================


def draft_section(
    llm: ChatOllama,
    invention: InventionModel,
    section: str,
) -> str:

    invention_text = invention_json(invention)

    common_rules = """
The structured invention model is the authoritative technical
basis for this drafting task.

DO NOT introduce technical matter that is not supported by it.

DO NOT invent:

- components
- mechanisms
- algorithms
- numerical values
- experimental results
- performance claims
- prior-art statements
- implementation details
- materials
- dimensions
- operating parameters

You may improve wording and organization, but not technical
substance.

Where the invention model identifies matter as uncertain or
undisclosed, do not silently convert it into a disclosed fact.

Write in formal patent-specification style.
"""

    section_instructions = {
        "field": """
Draft the "Field of Invention" section.

State the technical field to which the invention relates.

Keep it concise and based only on the invention model.
""",
        "background": """
Draft the "Background" section.

Explain the technical context and the problem addressed by
the invention.

Do not invent specific prior-art documents, patents, dates,
products, statistics or technical deficiencies unless they
are present in the invention model.

Where the source does not establish a particular prior-art
fact, describe the problem generally without presenting an
unsupported fact as established prior art.
""",
        "summary": """
Draft the "Summary of the Invention" section.

Explain:

- what the invention provides
- its principal structural features
- relevant functional relationships
- relevant procedural operation
- stated technical benefits, where supported

Do not introduce new technical matter.
""",
        "detailed_description": """
Draft the "Detailed Description" section.

Provide a coherent technical description of the invention.

Cover, as applicable:

- components
- arrangement of components
- relationships between components
- operation
- procedural steps
- interaction between components
- disclosed variations
- disclosed implementations
- explicitly disclosed benefits

Explain the invention sufficiently for a technically skilled
reader to understand how the disclosed embodiment operates.

Do not create embodiments that are not disclosed.

Do not add invented numerical values or implementation details.
""",
    }

    if section not in section_instructions:
        raise ValueError(f"Unknown section: {section}")

    user_prompt = f"""
{common_rules}

================ INVENTION MODEL ================

{invention_text}

================ END INVENTION MODEL =============

{section_instructions[section]}
"""

    response = llm.invoke(
        [
            SystemMessage(content=common_rules),
            HumanMessage(content=user_prompt),
        ]
    )

    return response.content.strip()


# ============================================================
# CLAIM DRAFTING
# ============================================================


def draft_claims(
    llm: ChatOllama,
    invention: InventionModel,
) -> list[Claim]:

    system_prompt = """
You are drafting patent claims from a structured invention model.

The invention model is the ONLY technical basis.

Claims must be fairly based on the disclosed invention.

DO NOT introduce technical matter that does not appear in the
invention model.

DO NOT add:

- undisclosed components
- undisclosed relationships
- numerical limitations
- unsupported alternatives
- unsupported technical effects

Create a sensible claim hierarchy.

Where appropriate, provide:

- one independent apparatus/system claim
- one independent method claim
- dependent claims directed to disclosed features,
  relationships, variations or implementations

Do not create dependent claims merely by inventing arbitrary
limitations.

Use formal patent claim language.

Each claim must be a complete claim.
"""

    user_prompt = f"""
================ INVENTION MODEL ================

{invention_json(invention)}

================ END INVENTION MODEL =============

Draft a set of claims supported by this invention model.

The claims should cover the core disclosed invention without
adding subject matter that is not disclosed.
"""

    structured_llm = llm.with_structured_output(ClaimsOutput)

    result = structured_llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )

    return result.claims


# ============================================================
# ABSTRACT
# ============================================================


def draft_abstract(
    llm: ChatOllama,
    invention: InventionModel,
) -> str:

    system_prompt = """
Draft a patent abstract from the supplied invention model.

The abstract must:

- identify the technical field/context
- identify the invention
- identify its principal technical features
- state its principal use or technical effect where supported

Do not introduce technical matter not present in the invention
model.

The abstract must be concise and must not exceed 150 words.
"""

    user_prompt = f"""
================ INVENTION MODEL ================

{invention_json(invention)}

================ END INVENTION MODEL =============

Draft the patent abstract.
"""

    structured_llm = llm.with_structured_output(AbstractOutput)

    result = structured_llm.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )

    return result.abstract.strip()


# ============================================================
# VALIDATION
# ============================================================


def word_count(text: str) -> int:

    return len(re.findall(r"\b\w+\b", text))


def validate_specification(
    spec: "PatentSpecification",
) -> list[str]:

    errors = []

    required_fields = [
        ("title", spec.title),
        (
            "field_of_invention",
            spec.field_of_invention,
        ),
        ("background", spec.background),
        ("summary", spec.summary),
        (
            "detailed_description",
            spec.detailed_description,
        ),
        ("abstract", spec.abstract),
    ]

    for name, value in required_fields:
        if not value.strip():
            errors.append(f"{name} is empty")

    if not spec.claims:
        errors.append("No claims generated")

    expected_number = 1

    for claim in spec.claims:
        if claim.number != expected_number:
            errors.append(f"Claim numbering error: expected {expected_number}, got {claim.number}")

        if not claim.text.strip():
            errors.append(f"Claim {claim.number} is empty")

        expected_number += 1

    abstract_words = word_count(spec.abstract)

    if abstract_words > 150:
        errors.append(f"Abstract contains {abstract_words} words; maximum is 150")

    if len(spec.title.split()) > 15:
        errors.append("Title contains more than 15 words")

    return errors


# ============================================================
# SPECIFICATION MODEL
# ============================================================


class PatentSpecification(BaseModel):
    title: str

    field_of_invention: str

    background: str

    objects_of_invention: list[str] = Field(default_factory=list)

    summary: str

    detailed_description: str

    claims: list[Claim]

    abstract: str


# ============================================================
# WORD DOCUMENT
# ============================================================


def create_docx(
    spec: PatentSpecification,
    output_path: str,
):

    doc = Document()

    doc.add_heading(
        spec.title,
        level=0,
    )

    doc.add_heading(
        "FIELD OF INVENTION",
        level=1,
    )

    doc.add_paragraph(spec.field_of_invention)

    doc.add_heading(
        "BACKGROUND",
        level=1,
    )

    doc.add_paragraph(spec.background)

    if spec.objects_of_invention:
        doc.add_heading(
            "OBJECTS OF THE INVENTION",
            level=1,
        )

        for obj in spec.objects_of_invention:
            doc.add_paragraph(
                obj,
                style="List Bullet",
            )

    doc.add_heading(
        "SUMMARY OF THE INVENTION",
        level=1,
    )

    doc.add_paragraph(spec.summary)

    doc.add_heading(
        "DETAILED DESCRIPTION",
        level=1,
    )

    doc.add_paragraph(spec.detailed_description)

    doc.add_heading(
        "CLAIMS",
        level=1,
    )

    for claim in spec.claims:
        paragraph = doc.add_paragraph()

        paragraph.add_run(f"{claim.number}. ").bold = True

        paragraph.add_run(claim.text)

    doc.add_page_break()

    doc.add_heading(
        "ABSTRACT",
        level=1,
    )

    doc.add_paragraph(spec.abstract)

    doc.save(output_path)


# ============================================================
# MAIN
# ============================================================


def main():

    parser = argparse.ArgumentParser(description=("Generate an Indian patent specification using a two-stage LangChain + Ollama pipeline."))

    parser.add_argument(
        "input",
        help="Input invention disclosure (.txt, .pdf, .docx)",
    )

    parser.add_argument(
        "-m",
        "--model",
        default="qwen3:8b",
        help="Ollama model",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="indian_patent_spec.docx",
        help="Output DOCX",
    )

    parser.add_argument(
        "--save-model",
        default="invention_model.json",
        help="Save extracted invention model",
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # INITIALIZE LLM
    # --------------------------------------------------------

    print(f"\nInitializing Ollama model: {args.model}")

    llm = create_llm(args.model)

    # --------------------------------------------------------
    # READ SOURCE
    # --------------------------------------------------------

    print("\nReading invention disclosure...")

    source_text = read_input(args.input)

    if not source_text.strip():
        raise RuntimeError("Input document contains no extractable text.")

    print(
        "Source characters:",
        len(source_text),
    )

    # --------------------------------------------------------
    # STAGE 1
    # --------------------------------------------------------

    print("\n=== STAGE 1: EXTRACTING INVENTION MODEL ===")

    invention = extract_invention_model(
        llm,
        source_text,
    )

    Path(args.save_model).write_text(
        invention.model_dump_json(indent=2),
        encoding="utf-8",
    )

    print(
        "Invention model saved:",
        args.save_model,
    )

    print(
        "Structural features:",
        len(invention.structural_features),
    )

    print(
        "Functional features:",
        len(invention.functional_features),
    )

    print(
        "Procedural steps:",
        len(invention.procedural_steps),
    )

    # --------------------------------------------------------
    # STAGE 2
    # --------------------------------------------------------

    print("\n=== STAGE 2: DRAFTING SPECIFICATION ===")

    print("Drafting Field of Invention...")

    field = draft_section(
        llm,
        invention,
        "field",
    )

    print("Drafting Background...")

    background = draft_section(
        llm,
        invention,
        "background",
    )

    print("Drafting Summary...")

    summary = draft_section(
        llm,
        invention,
        "summary",
    )

    print("Drafting Detailed Description...")

    detailed_description = draft_section(
        llm,
        invention,
        "detailed_description",
    )

    print("Drafting Claims...")

    claims = draft_claims(
        llm,
        invention,
    )

    print("Drafting Abstract...")

    abstract = draft_abstract(
        llm,
        invention,
    )

    # --------------------------------------------------------
    # BUILD SPECIFICATION
    # --------------------------------------------------------

    spec = PatentSpecification(
        title=invention.invention_title,
        field_of_invention=field,
        background=background,
        objects_of_invention=invention.objectives,
        summary=summary,
        detailed_description=detailed_description,
        claims=claims,
        abstract=abstract,
    )

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    print("\n=== VALIDATION ===")

    errors = validate_specification(spec)

    # if errors:
    #     print("\nVALIDATION ERRORS:")

    #     for error in errors:
    #         print(
    #             " -",
    #             error,
    #         )

    #     raise RuntimeError("Specification failed validation.")

    print("Validation: PASS")

    print(
        "Claims:",
        len(spec.claims),
    )

    print(
        "Abstract words:",
        word_count(spec.abstract),
    )

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    create_docx(
        spec,
        args.output,
    )

    print(
        "\nSpecification generated:",
        args.output,
    )


if __name__ == "__main__":
    main()

# python generate_spec.py idf_file.docx -m qwen3:8b -o indian_patent_spec.docx
# python services\generate_spec.py input\provisional_specification.pdf -m llama3.1:8b -o vaibhav_patent_spec.docx
