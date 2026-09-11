from pathlib import Path

import chromadb

from services.embedding_service import init_embeddings


CHROMA_DIRECTORY = Path("./data/cpc/chroma")

COLLECTION_NAME = "cpc_2026_08"


def main():

    print("=" * 70)
    print("CPC CHROMA DATABASE TEST")
    print("=" * 70)

    # ---------------------------------------------------------
    # Connect to Chroma
    # ---------------------------------------------------------

    client = chromadb.PersistentClient(path=str(CHROMA_DIRECTORY))

    collection = client.get_collection(name=COLLECTION_NAME)

    print(f"\nCollection : {COLLECTION_NAME}")

    print(f"Record count : {collection.count():,}")

    # ---------------------------------------------------------
    # Test 1: inspect records directly
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("TEST 1 — SAMPLE RECORDS")
    print("=" * 70)

    sample = collection.get(
        limit=10,
        include=[
            "documents",
            "metadatas",
        ],
    )

    for i in range(len(sample["ids"])):
        print("\n" + "-" * 70)

        print(f"ID: {sample['ids'][i]}")

        print(f"Metadata:\n{sample['metadatas'][i]}")

        print(f"\nDocument:\n{sample['documents'][i]}")

    # ---------------------------------------------------------
    # Test 2: exact CPC lookup
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("TEST 2 — EXACT CPC LOOKUP")
    print("=" * 70)

    test_codes = [
        "G01F23/00",
        "A47G19/00",
        "A61F2/00",
    ]

    for code in test_codes:
        print(f"\nSearching for CPC: {code}")

        result = collection.get(
            where={"cpc_code": code},
            include=[
                "documents",
                "metadatas",
            ],
        )

        if not result["ids"]:
            print("  NOT FOUND")

            continue

        for i in range(len(result["ids"])):
            metadata = result["metadatas"][i]

            print(f"  Code       : {metadata.get('cpc_code')}")

            print(f"  Title      : {metadata.get('title')}")

            print(f"  Parent     : {metadata.get('parent_code')}")

            print(f"  Ancestors  : {metadata.get('ancestor_codes')}")

            print(f"  Level      : {metadata.get('level')}")

    # ---------------------------------------------------------
    # Test 3: semantic retrieval
    # ---------------------------------------------------------

    print("\n" + "=" * 70)
    print("TEST 3 — SEMANTIC RETRIEVAL")
    print("=" * 70)

    embedding_function = init_embeddings()

    test_queries = [
        "liquid level measurement",
        "liquid quantity measurement",
        "drinking vessel beverage container",
        "fluid consumption monitoring",
        "measuring amount of liquid consumed",
        "personalized hydration requirement",
        "adaptive hydration recommendation",
        "temperature and activity based hydration monitoring",
    ]

    for query in test_queries:
        print("\n" + "-" * 70)

        print(f"QUERY: {query}")

        query_embedding = embedding_function.embed_query(query)

        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=10,
            include=[
                "documents",
                "metadatas",
                "distances",
            ],
        )

        ids = result["ids"][0]
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]

        for i in range(len(ids)):
            metadata = metadatas[i]

            print(f"\n{i + 1}. {metadata.get('cpc_code')}")

            print(f"   Distance: {distances[i]}")

            print(f"   Title: {metadata.get('title')}")

            print(f"   Parent: {metadata.get('parent_code')}")

            print(f"   Ancestors: {metadata.get('ancestor_codes')}")


if __name__ == "__main__":
    main()
