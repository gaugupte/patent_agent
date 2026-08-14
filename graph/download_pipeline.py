import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import os

# 1. SETUP: Create local directory
os.makedirs("./global_patent_corpus", exist_ok=True)

# 2. LOAD DATA: Read your spreadsheet containing mixed US and EP numbers
df = pd.read_csv("us_fly.csv")
patent_list = df["PatentNumber"].tolist()

print(f"Starting download for {len(patent_list)} global patents...")

# 3. AUTOMATION LOOP
for pid in patent_list:
    # Clean up formatting strings (removes spaces, hyphens, slashes, commas)
    clean_id = (
        str(pid)
        .replace("-", "")
        .replace(",", "")
        .replace(" ", "")
        .replace("/", "")
        .strip()
    )

    # Target root URL without forcing '/en' to support multilingual EPO filings
    url = f"https://patents.google.com/patent/{clean_id}"
    print(url)

    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})

        # If a plain ID fails (like a raw EP number), try appending a default 'A1' application tag
        if (
            response.status_code != 200
            and clean_id.upper().startswith("EP")
            and not clean_id.endswith(("A1", "A2", "B1"))
        ):
            fallback_id = f"{clean_id}A1"
            url = f"https://google.com{fallback_id}"
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code == 200:
                clean_id = fallback_id

        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "html.parser")

            # Extract full text divisions
            # abstract_box = soup.find("div", {"itemprop": "abstract"})
            abstract_box = (
                soup.find("section", {"itemprop": "abstract"})
                or soup.find("div", {"itemprop": "abstract"})
                or soup.find("abstract")
                or soup.find(
                    "meta", {"name": "DC.description"}
                )  # Fallback to meta tags if hidden
            )
            claims_box = soup.find("section", {"itemprop": "claims"})
            desc_box = soup.find("section", {"itemprop": "description"})

            text_data = f"PATENT ID: {clean_id}\nURL: {url}\n\n"
            if abstract_box:
                text_data += f"--- ABSTRACT ---\n{abstract_box.get_text()}\n\n"
            if claims_box:
                text_data += f"--- CLAIMS ---\n{claims_box.get_text()}\n\n"
            if desc_box:
                text_data += f"--- DESCRIPTION ---\n{desc_box.get_text()}\n"

            if claims_box or desc_box:
                with open(
                    f"./global_patent_corpus/{clean_id}.txt", "w", encoding="utf-8"
                ) as f:
                    f.write(text_data)
                print(f"Success: Saved text for {clean_id}")
            else:
                print(f"Warning: Page loaded but text container empty for {clean_id}")
        else:
            print(f"Failed: HTTP Error {response.status_code} for {clean_id}")

        # Maintain a safe 2-second rate-limiting buffer for international servers
        time.sleep(2.0)

    except Exception as e:
        print(f"Critical error on {clean_id}: {e}")

print("\n--- Pipeline Complete ---")


"""
# following is the code for translation of the downloaded patents to English.

# Install via terminal: pip install deep-translator
from deep-translator import GoogleTranslator

# Inside your scraping loop, after extracting desc_box.get_text():
raw_description = desc_box.get_text()

# Check if the text is long and looks like German/French (or parse language tags)
# If it's not English, translate it in chunks (Google has a 5000 character limit per request)
def translate_large_text(text):
    translator = GoogleTranslator(source='auto', target='en')
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    translated_chunks = [translator.translate(chunk) for chunk in chunks]
    return " ".join(translated_chunks)

# Run the clean translation
english_description = translate_large_text(raw_description)



"""
