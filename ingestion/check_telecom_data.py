import chromadb
from sentence_transformers import CrossEncoder

# 1. Connect to your database
chroma_client = chromadb.PersistentClient(path="./data/chroma_db/full_cpc_db")
collection = chroma_client.get_collection(name="cpc_patent_classification")

# 2. Explicitly pull the data for H04W and C04B to see what is stored
test_disclosure = "Systems and methods are provided for establishing a backhaul connection in a wireless network..."

print("=== DIRECT DATABASE RAW CONTENET CHECK ===")

# Try to pull your wireless category directly
h_data = collection.get(ids=["H04W"])
c_data = collection.get(ids=["C04B41/4972"])

if h_data and h_data["documents"]:
    print("\n[H04W Raw Text Stored in DB]:")
    print(h_data["documents"][0][:300] + "...")
else:
    print("\n❌ H04W contains NO text descriptions inside the DB.")

if c_data and c_data["documents"]:
    print("\n[C04B41/4972 Raw Text Stored in DB]:")
    print(c_data["documents"][0][:300] + "...")

# 3. Direct Rerank Test
# If H04W text exists, let's force the Cross-Encoder to grade them side-by-side
if h_data["documents"] and c_data["documents"]:
    print("\n=== CROSS-ENCODER FORCE RE-RANK TEST ===")
    reranker = CrossEncoder("BAAI/bge-reranker-large")

    pairs = [[test_disclosure, h_data["documents"][0]], [test_disclosure, c_data["documents"][0]]]
    scores = reranker.predict(pairs)
    print(f"Score for H04W (Wireless): {scores[0]:.4f}")
    print(f"Score for C04B (Chemistry): {scores[1]:.4f}")
