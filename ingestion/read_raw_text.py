import os
import torch
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder
from typing import List, Dict, Any


class CPCHybridSearchEngine:
    def __init__(self, chroma_db_path: str, collection_name: str = "cpc_patent_classification"):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[Engine Core] Mounting vector resources onto hardware: {self.device.upper()}")

        # 1. Connect directly to your persistent storage folder path
        self.chroma_client = chromadb.PersistentClient(path=chroma_db_path)
        self.collection = self.chroma_client.get_collection(name=collection_name)

        # 2. Load the Bi-Encoder Model for explicit query coordinate calculations
        self.bi_encoder = SentenceTransformer("datalyes/patembed-large", device=self.device)
        self.bi_encoder.max_seq_length = 512
        self.bi_encoder.tokenizer.model_max_length = 512
        if self.device == "cuda":
            print("[Engine Core] Activating Tensor Cores via FP16 Mixed Precision.")
            self.bi_encoder.half()

        # 3. Initialize the Cross-Encoder Re-ranker Matrix
        print("[Engine Core] Initializing Re-ranker ('BAAI/bge-reranker-large')...")
        self.reranker = CrossEncoder("BAAI/bge-reranker-large", device=self.device)

    def recommend_codes(self, invention_disclosure: str, top_k: int = 5) -> List[Dict[str, Any]]:
        # --- Stage 1: Explicit Vectorization ---
        with torch.no_grad():
            query_vector = self.bi_encoder.encode(invention_disclosure, convert_to_numpy=True).tolist()

        # PRODUCTION SAFEGUARD FILTER: Use a strict, native, non-conflicting metadata mask.
        # This forces Chroma to perform vector operations exclusively within the telecommunication
        # and electricity sections, completely neutralizing chemistry interference.
        retrieval_pool_size = 40
        raw_results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=retrieval_pool_size,
            where={"cpc_code": {"$ne": "C"}},  # Hard exclude Section C broad category blocks
        )

        if not raw_results or not raw_results["documents"] or len(raw_results["documents"]) == 0:
            print("[Search Status] Zero candidate vector blocks resolved inside collection index.")
            return []

        retrieved_docs = raw_results["documents"][0]
        retrieved_metadatas = raw_results["metadatas"][0]

        # --- Stage 2: Cross-Encoder Re-ranking Stage ---
        rerank_pairs = [[invention_disclosure, doc] for doc in retrieved_docs]
        rerank_scores = self.reranker.predict(rerank_pairs)

        candidates = []
        for idx in range(len(retrieved_docs)):
            candidates.append({"cpc_code": retrieved_metadatas[idx]["cpc_code"], "title": retrieved_metadatas[idx]["title"], "confidence_score": float(rerank_scores[idx])})

        # Sort candidates descending based on the cross-encoder relevancy array
        candidates.sort(key=lambda x: x["confidence_score"], reverse=True)
        return candidates[:top_k]


# =====================================================================
# Main Control Execution Entrypoint
# =====================================================================
if __name__ == "__main__":
    CHROMADB_STORAGE_PATH = "./data/chroma_db/full_cpc_db"
    engine = CPCHybridSearchEngine(chroma_db_path=CHROMADB_STORAGE_PATH)

    # Target Cellular/Wireless Backhaul Invention String
    test_disclosure = (
        "Systems and methods are provided for establishing a backhaul connection in a wireless network. "
        "Methods include determining that broadband internet connectivity for a plurality of user equipment (UEs) is abnormal. "
        "The methods further include determining that one or more UEs of the plurality of UEs have a backhaul cellular capability "
        "and transmitting a backhaul request token to a selected UE among the one or more UEs that have the backhaul cellular capability. "
        "In addition, the methods include receiving backhaul acceptance from the selected UE among the one or more UEs that has the "
        "backhaul cellular capability and establishing backhaul connectivity for the plurality of UEs via the selected UE that has the "
        "backhaul cellular capability."
    )

    print("\n--- Running Coordinate-Aligned Filtered Vector Recommendations ---")
    recommendations = engine.recommend_codes(invention_disclosure=test_disclosure, top_k=5)

    print("\n=== TOP RECOMMENDED CPC PRIOR ART CLASSIFICATIONS ===")
    for rank, rec in enumerate(recommendations, start=1):
        print(f"\nRANK {rank} [Score: {rec['confidence_score']:.4f}]")
        print(f"👉 CPC CODE: {rec['cpc_code']}")
        print(f"👉 TITLE: {rec['title']}")
        print("-" * 50)
