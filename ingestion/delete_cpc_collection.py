from langchain_chroma import Chroma

CHROMA_PATH = "../data/chroma"
COLLECTION_NAME = "cpc_2026_08"

vector_store = Chroma(
    collection_name=COLLECTION_NAME,
    persist_directory=CHROMA_PATH,
)

vector_store.delete_collection()

print("CPC collection deleted.")
