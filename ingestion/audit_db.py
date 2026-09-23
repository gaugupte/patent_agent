import glob
import os

files = glob.glob("./cpc_files/definitions_202608/*.xml")
if not files:
    print("❌ ERROR: No XML files found in ./cpc_definitions")
    exit()

target_file = files[0]
print(f"Reading raw file data from: {target_file}")

with open(target_file, mode="r", encoding="utf-8") as f:
    # Read just the first 2500 characters of raw text to see the absolute tag names
    raw_text = f.read(2500)

print("\n--- RAW XML CHARACTERS START ---")
print(raw_text)
print("--- RAW XML CHARACTERS END ---")


# import xml.etree.ElementTree as ET
# import os

# file_path = "./cpc_files/definitions_202608/cpc-definition-A01B.xml"

# if not os.path.exists(file_path):
#     # Try finding any file in your folder if naming is slightly different
#     import glob

#     files = glob.glob("./cpc_files/definitions_202608/*.xml")
#     if files:
#         file_path = files[0]

# print(f"Auditing file structure for: {file_path}")
# tree = ET.parse(file_path)
# root = tree.getroot()

# # Let's count EVERY single tag inside this file to see what it is named
# all_tags = [elem.tag.split("}")[-1] for elem in root.iter()]
# from collections import Counter

# print("\nTag frequencies inside this file:")
# for tag, count in Counter(all_tags).most_common(10):
#     print(f" - <{tag}>: found {count} times")


# # import chromadb

# # chroma_client = chromadb.PersistentClient(path="./data/chroma/full_cpc_db")
# # collection = chroma_client.get_collection(name="cpc_patent_classification")

# # print("=== CHROMADB INSIGHTS ===")
# # print(f"Total documents inside database: {collection.count()}")

# # # Fetch a random small sample of stored records
# # sample = collection.get(limit=5)
# # print("\nSample IDs in DB:", sample["ids"])
