from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import chromadb
from langchain_huggingface import HuggingFaceEmbeddings

from ingestion.cpc_parser import CPCValidationResult, parse_cpc_directory, print_sample_records, print_validation_report

# =============================================================================
# DEFAULTS
# =============================================================================

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_CHROMA_DIR = "data/chroma/cpc"
DEFAULT_COLLECTION = "cpc_2026_08"
DEFAULT_BATCH_SIZE = 512

# =============================================================================
# ARGUMENTS
# =============================================================================


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=("Parse, validate, normalize and ingest CPC XML data into Chroma."))
    parser.add_argument("xml_directory", type=str, help="Directory containing CPC XML files.")
    parser.add_argument("--validate-only", action="store_true", help=("Parse and validate CPC data without creating or modifying Chroma."))
    parser.add_argument("--chroma-dir", type=str, default=DEFAULT_CHROMA_DIR, help=(f"Persistent Chroma directory. Default: {DEFAULT_CHROMA_DIR}"))
    parser.add_argument("--collection", type=str, default=DEFAULT_COLLECTION, help=(f"Chroma collection name. Default: {DEFAULT_COLLECTION}"))
    parser.add_argument("--embedding-model", type=str, default=DEFAULT_EMBEDDING_MODEL, help=(f"Sentence-transformers embedding model. Default: {DEFAULT_EMBEDDING_MODEL}"))
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=(f"Number of records embedded per batch. Default: {DEFAULT_BATCH_SIZE}"))
    parser.add_argument("--keep-normalized", action="store_true", help=("Keep normalized CPC JSON after ingestion."))
    return parser


# =============================================================================
# NORMALIZED JSON
# =============================================================================


def save_normalized_records(records, output_path: Path) -> None:

    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = [record.model_dump() for record in records.values()]

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Normalized records saved to: {output_path}")


# =============================================================================
# METADATA
# =============================================================================


def build_metadata(record) -> dict:

    metadata = {
        "code": record.code,
        "title": record.title,
        "level": (record.level if record.level is not None else -1),
        "parent_code": (record.parent_code or ""),
        "source_file": (record.source_file or ""),
        "publication_date": (record.publication_date or ""),
        "status": (record.status or ""),
        "section": (record.section or ""),
        "class_code": (record.class_code or ""),
        "subclass_code": (record.subclass_code or ""),
        "main_group_code": (record.main_group_code or ""),
        "not_allocatable": bool(record.not_allocatable),
        "additional_only": bool(record.additional_only),
        "definition_exists": bool(record.definition_exists),
        "ipc_concordant": bool(record.ipc_concordant),
        "source_occurrences": int(record.source_occurrences),
    }
    # Chroma metadata values should remain scalar.
    #
    # Store hierarchy as a compact string rather than a Python list.
    metadata["hierarchy_codes"] = " > ".join(record.hierarchy_codes)
    metadata["ancestor_codes"] = " > ".join(record.ancestor_codes)

    return metadata


# =============================================================================
# SEMANTIC DOCUMENT
# =============================================================================


def build_semantic_document(record) -> str:
    """
    Build the text that is actually embedded.

    IMPORTANT:
    We deliberately use the clean CPC title and hierarchy only.

    We do NOT embed:
        - references
        - warnings
        - CPC-specific administrative information
        - raw XML
        - descendant titles

    This keeps semantic retrieval focused on the classification.
    """

    parts = [f"CPC {record.code}"]

    if record.title:
        parts.append(f"Title: {record.title}")

    hierarchy_titles = [title for title in record.hierarchy_titles if title]

    if hierarchy_titles:
        parts.append("Classification hierarchy: " + " > ".join(hierarchy_titles))

    if record.parent_title:
        parts.append("Parent classification: " + record.parent_title)

    return "\n\n".join(parts)


# =============================================================================
# CHROMA RESET
# =============================================================================


def reset_chroma_directory(chroma_dir: Path) -> None:

    if not chroma_dir.exists():
        return

    print()
    print(f"Removing existing Chroma directory:")
    print(f"  {chroma_dir}")

    shutil.rmtree(chroma_dir)


# =============================================================================
# CHROMA CLIENT
# =============================================================================


def create_chroma_client(chroma_dir: Path):

    chroma_dir.mkdir(parents=True, exist_ok=True)
    print()
    print("Creating persistent Chroma client...")
    client = chromadb.PersistentClient(path=str(chroma_dir))
    return client


# =============================================================================
# COLLECTION
# =============================================================================


def create_collection(client, collection_name: str, embedding_model: str):

    print(f"Creating collection: {collection_name}")
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={
            "description": ("Canonical CPC classification semantic index"),
            "embedding_model": embedding_model,
            "distance_metric": "cosine",
        },
    )

    return collection


# =============================================================================
# EMBEDDINGS
# =============================================================================


def create_embeddings(
    embedding_model: str,
):

    print()
    print("Loading embedding model:")
    print(f"  {embedding_model}")

    embeddings = HuggingFaceEmbeddings(
        model_name=embedding_model,
        model_kwargs={
            "device": "cpu",
        },
        encode_kwargs={
            "normalize_embeddings": True,
        },
    )

    return embeddings


# =============================================================================
# INGESTION
# =============================================================================


def ingest_records(records, collection, embeddings, batch_size: int) -> None:

    total = len(records)

    print()
    print(f"Starting embedding ingestion for {total:,} CPC records...")

    records_list = list(records.values())

    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch = records_list[start:end]
        documents = [build_semantic_document(record) for record in batch]
        ids = [record.code for record in batch]
        metadatas = [build_metadata(record) for record in batch]

        # -------------------------------------------------------------
        # Embed with LangChain's embedding model.
        #
        # IMPORTANT:
        # We pass the resulting vectors to native Chroma.
        #
        # We do NOT pass HuggingFaceEmbeddings as Chroma's
        # embedding_function.
        # -------------------------------------------------------------

        vectors = embeddings.embed_documents(documents)

        collection.add(ids=ids, documents=documents, embeddings=vectors, metadatas=metadatas)

        print(f"  Ingested {end:,}/{total:,} ({end / total * 100:.1f}%)")

    print()
    print("Embedding ingestion complete.")


# =============================================================================
# VERIFICATION
# =============================================================================


def verify_collection(collection, expected_count: int) -> None:

    actual_count = collection.count()
    print()
    print("=" * 80)
    print("CHROMA VERIFICATION")
    print("=" * 80)
    print(f"Expected records : {expected_count:,}")
    print(f"Chroma records   : {actual_count:,}")
    if actual_count != expected_count:
        raise RuntimeError("Chroma record count does not match the number of canonical CPC records.")

    print("COUNT CHECK: PASS")


# =============================================================================
# SANITY SEARCH
# =============================================================================


def run_sanity_search(collection, embeddings, query: str, k: int = 5) -> None:

    print()
    print("-" * 80)
    print(f"QUERY: {query}")
    print("-" * 80)

    query_embedding = embeddings.embed_query(query)

    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    documents = result.get("documents", [[]])[0]

    metadatas = result.get("metadatas", [[]])[0]

    distances = result.get(
        "distances",
        [[]],
    )[0]

    for index, document in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) else {}
        distance = distances[index] if index < len(distances) else None
        print()
        print(f"{index + 1}. {metadata.get('code', '?')}")
        print(f"   Title: {metadata.get('title', '')}")
        if distance is not None:
            print(f"   Distance: {distance:.4f}")


def run_sanity_queries(collection, embeddings) -> None:

    queries = [
        "liquid level measurement",
        "drinking vessel or cup",
        "soil working agricultural machine",
    ]

    print()
    print("=" * 80)
    print("SEMANTIC SANITY SEARCH")
    print("=" * 80)

    for query in queries:
        run_sanity_search(collection, embeddings, query, k=5)


# =============================================================================
# MAIN
# =============================================================================


def main() -> int:

    parser = build_argument_parser()
    args = parser.parse_args()
    xml_directory = Path(args.xml_directory)
    chroma_dir = Path(args.chroma_dir)

    # -------------------------------------------------------------------------
    # Validate arguments
    # -------------------------------------------------------------------------

    if args.batch_size <= 0:
        parser.error("--batch-size must be greater than zero")

    if not xml_directory.exists():
        print(
            f"ERROR: XML directory does not exist: {xml_directory}",
            file=sys.stderr,
        )

        return 1

    # -------------------------------------------------------------------------
    # Parse + validate CPC
    # -------------------------------------------------------------------------

    print()
    print("=" * 80)
    print("CPC INGESTION")
    print("=" * 80)
    print(f"XML directory : {xml_directory}")
    print(f"Chroma dir    : {chroma_dir}")
    print(f"Collection    : {args.collection}")
    print(f"Embedding     : {args.embedding_model}")
    print(f"Batch size    : {args.batch_size}")
    print()
    print("Parsing CPC XML...")

    records, validation = parse_cpc_directory(xml_directory)
    print_validation_report(validation)

    # -------------------------------------------------------------------------
    # Samples
    # -------------------------------------------------------------------------

    print_sample_records(records)

    # -------------------------------------------------------------------------
    # Validation gate
    #
    # NOTHING has touched Chroma yet.
    # -------------------------------------------------------------------------

    if not validation.valid:
        print()
        print("ERROR: CPC validation failed.")
        print("Chroma was NOT modified.")
        return 1

    # -------------------------------------------------------------------------
    # Validate-only mode
    # -------------------------------------------------------------------------

    if args.validate_only:
        print()
        print("=" * 80)
        print("VALIDATION-ONLY MODE")
        print("=" * 80)
        print("No embeddings created.")
        print("No Chroma database modified.")
        return 0

    # -------------------------------------------------------------------------
    # Save normalized data
    # -------------------------------------------------------------------------

    normalized_path = chroma_dir.parent / "cpc_normalized.json"

    save_normalized_records(records, normalized_path)

    # -------------------------------------------------------------------------
    # Create embeddings
    # -------------------------------------------------------------------------

    embeddings = create_embeddings(args.embedding_model)

    # -------------------------------------------------------------------------
    # IMPORTANT:
    #
    # Only now do we destroy the existing Chroma directory.
    #
    # Validation has already passed.
    # -------------------------------------------------------------------------

    reset_chroma_directory(chroma_dir)

    # -------------------------------------------------------------------------
    # Create Chroma
    # -------------------------------------------------------------------------

    client = create_chroma_client(chroma_dir)
    collection = create_collection(client, args.collection, args.embedding_model)

    # -------------------------------------------------------------------------
    # Ingest
    # -------------------------------------------------------------------------

    ingest_records(records, collection, embeddings, args.batch_size)

    # -------------------------------------------------------------------------
    # Verify
    # -------------------------------------------------------------------------

    verify_collection(collection, len(records))

    # -------------------------------------------------------------------------
    # Semantic sanity tests
    # -------------------------------------------------------------------------

    run_sanity_queries(collection, embeddings)

    # -------------------------------------------------------------------------
    # Normalized JSON cleanup
    # -------------------------------------------------------------------------

    if not args.keep_normalized:
        try:
            normalized_path.unlink()

            print()
            print("Temporary normalized JSON removed.")

        except FileNotFoundError:
            pass

    # -------------------------------------------------------------------------
    # Done
    # -------------------------------------------------------------------------

    print()
    print("=" * 80)
    print("CPC INGESTION COMPLETE")
    print("=" * 80)

    print(f"Records indexed : {collection.count():,}")
    print(f"Collection      : {args.collection}")
    print(f"Chroma location : {chroma_dir}")
    print("Status          : SUCCESS")
    return 0


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    sys.exit(main())
