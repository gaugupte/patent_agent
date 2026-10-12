import os
import glob
import re
import csv
from tqdm import tqdm


def scrape_xml_with_absolute_finality(definition_dir: str, output_csv_path: str):
    all_files = glob.glob(os.path.join(definition_dir, "*.xml"))
    def_files = [f for f in all_files if "definition" in os.path.basename(f)]

    if not def_files:
        print(f"[Error] No definition XML files discovered in: {definition_dir}")
        return

    print(f"--- [Stage 1] Executing Dual-Gate Split Extraction Pass (Clean Suffix) ---")

    with open(output_csv_path, mode="w", encoding="utf-8", newline="") as csv_file:
        fieldnames = ["clean_id", "raw_symbol", "title", "rag_content"]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        total_records = 0

        for file_path in def_files:
            try:
                with open(file_path, mode="r", encoding="utf-8") as f:
                    file_content = f.read()

                # Split the entire file on the hard closing delimiter tag
                raw_items = file_content.split("</definition-item>")

                for item_chunk in raw_items:
                    if "<definition-item" not in item_chunk:
                        continue

                    # Safe extraction of the active item block boundary frames
                    item_text = item_chunk.split("<definition-item", 1)[-1]

                    # 1. NATIVE SYMBOL EXTRACTION GATE
                    symbol_match = re.search(r"<classification-symbol.*?>(.*?)</classification-symbol>", item_text, re.DOTALL)
                    if not symbol_match:
                        continue
                    raw_symbol = symbol_match.group(1).strip()
                    raw_symbol = re.sub(r"<.*?>", "", raw_symbol).strip()

                    # Form the exact, un-truncated lookup key identifier
                    clean_id = re.sub(r"\s+", "", raw_symbol).strip().upper()
                    if not clean_id:
                        continue

                    # 2. PROACTIVE ATTRIBUTE PURGING PASS
                    # Strips out remaining opening bracket attributes (e.g., date-revised="2026-01-01">)
                    clean_item_body = re.sub(r"^.*?>", "", item_text, count=1).strip()

                    # 3. TOTAL TEXT EXTRACTION GATE
                    # Strip out every single raw XML bracket inside the item block cleanly
                    plain_text = re.sub(r"<[^>]*>", " ", clean_item_body)
                    plain_text = re.sub(r"\s+", " ", plain_text).strip()

                    # Extract a clean preview title string from the title block directly
                    title_match = re.search(r"<definition-title.*?>(.*?)</definition-title>", clean_item_body, re.DOTALL)
                    if title_match:
                        title_text = re.sub(r"<[^>]*>", "", title_match.group(1)).strip()
                        title_text = re.sub(r"\s+", " ", title_text)
                    else:
                        title_text = " ".join(plain_text.split(" ")[:10])

                    # Compile a completely flat row string with NO raw line breaks to prevent truncation
                    rag_content = f"CPC CODE: {raw_symbol} | COMPLETE PRIOR ART DATA TEXT CONTEXT: {plain_text}"

                    writer.writerow({"clean_id": str(clean_id), "raw_symbol": str(raw_symbol), "title": str(title_text)[:250], "rag_content": str(rag_content)})
                    total_records += 1

            except Exception:
                continue

    print(f"\n[Success] Complete Rich CSV generated: '{output_csv_path}'")
    print(f"[Success] Total valid records extracted: {total_records}")


if __name__ == "__main__":
    DEFINITION_XML_DIR = "./cpc_files/definitions_202608"
    OUTPUT_CSV_FILE = "./cpc_extracted_data.csv"
    scrape_xml_with_absolute_finality(definition_dir=DEFINITION_XML_DIR, output_csv_path=OUTPUT_CSV_FILE)
