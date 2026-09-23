import os
import csv
import torch
import chromadb
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
import sys


# =====================================================================
# Native Chroma Embedding Function Alignment Layer
# =====================================================================
class ProductionPatentEmbeddingFunction(EmbeddingFunction):
    """Custom embedding function wrapper enforcing exact 1024-dimension shapes.

    Locks tokenizer context parameters to a strict 512 matrix window.
    """

    def __init__(self, model_name: str = "datalyes/patembed-large"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[Hardware Core] Initializing '{model_name}' on target: {self.device.upper()}")

        # Load the target embedding model
        self.model = SentenceTransformer(model_name, device=self.device)

        # Hard lock context truncation boundaries to prevent matrix shape crashes
        self.model.max_seq_length = 512
        self.model.tokenizer.model_max_length = 512

        if self.device == "cuda":
            print("[Hardware Core] Activating Tensor Cores via FP16 Mixed Precision mode.")
            self.model.half()

    def __call__(self, input_texts: Documents) -> Embeddings:
        """Executed automatically by Chroma during database write transitions."""
        embeddings = self.model.encode(
            input_texts,
            batch_size=128,  # Large batch size maximizes RTX 4050 processing speeds
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return embeddings.tolist()


# =====================================================================
# High-Throughput CSV to Database Loader Engine
# =====================================================================
def load_csv_to_chroma(csv_path: str, chroma_db_path: str, collection_name: str = "cpc_patent_classification"):
    csv.field_size_limit(100 * 1024 * 1024)  # Sets a strict, massive 100MB per-cell ceiling limit
    if not os.path.exists(csv_path):
        print(f"[Error] Source extract file could not be found: {csv_path}")
        return

    print("\n--- Starting High-Throughput Chroma Vector Generation Pass ---")

    # Connect directly to your persistent storage path directory
    chroma_client = chromadb.PersistentClient(path=chroma_db_path)

    # Safely purge older conflicting configuration files to prevent metadata traps
    try:
        chroma_client.delete_collection(name=collection_name)
        print(f"[Database Client] Stale database states cleared completely.")
    except Exception:
        pass

    # Instantiate the custom embedding logic block
    embedding_logic = ProductionPatentEmbeddingFunction()

    # CRITICAL ADVANTAGE: Bind the custom model parameter natively on collection initialization
    print(f"[Database Client] Generating fresh collection configuration layout...")
    collection = chroma_client.create_collection(name=collection_name, embedding_function=embedding_logic)

    # Ingestion transactional chunk buffers
    documents = []
    metadatas = []
    ids = []

    # Count rows beforehand to establish an accurate tqdm progress bar tracker
    with open(csv_path, mode="r", encoding="utf-8") as f:
        total_rows = sum(1 for _ in f) - 1  # Subtract the header row

    print(f"[Loader Engine] Commencing ingestion run for {total_rows} aligned rows...")

    with open(csv_path, mode="r", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)

        # Read the spreadsheet row-by-row with perfect index parameter alignment
        for row in tqdm(reader, total=total_rows, desc="Vectorising data on GPU"):
            documents.append(row["rag_content"])
            metadatas.append({"cpc_code": str(row["raw_symbol"]), "title": str(row["title"])})
            ids.append(str(row["clean_id"]))

            # Commit items in blocks of 4000 to keep well below the SQLite parameter limit
            if len(documents) >= 4000:
                collection.add(documents=documents, metadatas=metadatas, ids=ids)
                documents, metadatas, ids = [], [], []

        # Flush out any remaining items from the buffer loops
        if documents:
            collection.add(documents=documents, metadatas=metadatas, ids=ids)

    print(f"\n[Success] Vector store database population phase complete.")
    print(f"[Success] Total persistent records successfully written to drive: {collection.count()}")


if __name__ == "__main__":
    # 1. Get the directory where THIS script file is physically located (ingestion folder)
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    # 2. Safely jump one directory level UP to find the patent_agent root folder
    ROOT_DIR = os.path.dirname(SCRIPT_DIR)

    # 3. Path Management
    # Resolves paths dynamically relative to the execution origin point
    SOURCE_CSV_FILE = os.path.join(ROOT_DIR, "cpc_extracted_data.csv")
    CHROMADB_STORAGE_PATH = os.path.join(ROOT_DIR, "data", "chroma_db", "full_cpc_db")

    load_csv_to_chroma(csv_path=SOURCE_CSV_FILE, chroma_db_path=CHROMADB_STORAGE_PATH)
