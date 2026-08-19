import argparse
from pathlib import Path
import xml.etree.ElementTree as ET

from langchain_core.documents import Document
from langchain_chroma import Chroma

from services.embedding_service import init_embeddings

CPC_VERSION = "2026.08"
COLLECTION_NAME = "cpc_2026_08"
CHROMA_PATH = "./data/chroma"
CHROMA_BATCH_SIZE = 5000


def clean_text(element):
    parts = []

    for child in element.iter():
        tag = child.tag.split("}")[-1]

        if tag == "reference":
            continue

        if child.text:
            text = child.text.strip()

            if text:
                parts.append(text)

    return " ".join(parts)


def parse_cpc_xml(xml_file):

    documents = []
    stack = []

    for event, elem in ET.iterparse(xml_file, events=("start", "end")):
        tag = elem.tag.split("}")[-1]

        if event == "start":
            if tag == "classification-item":
                stack.append(elem)

            continue

        # -----------------------------------------
        # Process classification-item
        # -----------------------------------------

        if tag != "classification-item":
            continue

        symbol_element = elem.find(".//classification-symbol")

        if symbol_element is None:
            if stack:
                stack.pop()

            elem.clear()
            continue

        cpc_code = symbol_element.text.strip()

        level = elem.attrib.get("level")

        title_element = elem.find("class-title")

        title = ""

        if title_element is not None:
            title = clean_text(title_element)

        # Parent classification
        parent_code = None

        if len(stack) > 1:
            parent = stack[-2]

            parent_symbol = parent.find(".//classification-symbol")

            if parent_symbol is not None:
                parent_code = parent_symbol.text.strip()

        metadata = {
            "cpc_code": cpc_code,
            "level": int(level) if level else None,
            "parent_code": parent_code,
            "status": elem.attrib.get("status"),
            "definition_exists": elem.attrib.get("definition-exists"),
            "ipc_concordant": elem.attrib.get("ipc-concordant"),
            "date_revised": elem.attrib.get("date-revised"),
            "cpc_version": CPC_VERSION,
        }

        text = f"CPC classification: {cpc_code}\nTitle: {title}\n"

        if parent_code:
            text += f"Parent classification: {parent_code}\n"

        documents.append(
            Document(
                page_content=text,
                metadata=metadata,
            )
        )

        stack.pop()
        elem.clear()

    return documents


def ingest_cpc_directory(xml_directory):

    xml_directory = Path(xml_directory)

    if not xml_directory.exists():
        raise FileNotFoundError(f"CPC directory does not exist: {xml_directory}")

    xml_files = sorted(xml_directory.glob("*.xml"))

    if not xml_files:
        raise ValueError(f"No XML files found in {xml_directory}")

    print(f"Found {len(xml_files)} CPC XML files.")

    embeddings = init_embeddings()

    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=CHROMA_PATH,
        embedding_function=embeddings,
    )

    total_documents = 0

    for xml_file in xml_files:
        print(f"Processing: {xml_file.name}")
        documents = parse_cpc_xml(xml_file)
        if documents:
            for i in range(0, len(documents), CHROMA_BATCH_SIZE):
                batch = documents[i : i + CHROMA_BATCH_SIZE]
                vector_store.add_documents(batch)
                print(f"  Added batch {i + 1}-{i + len(batch)}")
        else:
            print("  No classifications found")
        total_documents += len(documents)
        print(f"  Added {len(documents)} classifications")

    print("--------------------------------")
    print("CPC ingestion completed")
    print(f"Files processed: {len(xml_files)}")
    print(f"Classifications added: {total_documents}")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Chroma path: {CHROMA_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--directory",
        required=True,
        help="Directory containing CPC XML files",
    )

    args = parser.parse_args()

    ingest_cpc_directory(args.directory)
