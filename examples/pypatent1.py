import os
import time
import pandas as pd
import pypatent
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# 1. SETUP: Create local directory to hold the downloaded dataset
os.makedirs("./pypatent_fulltext_corpus", exist_ok=True)

# 2. DATA PROCESSING: Read your spreadsheet
df = pd.read_csv("us_fly.csv")  # Assumes column name is 'PatentNumber'
raw_patent_list = df["PatentNumber"].tolist()

# 3. CONFIGURE CHROME HEADLESS DRIVER
# Enforces a silent background operation so no browser windows pop open on your screen
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")

# Explicitly spin up the driver session
driver = webdriver.Chrome(options=chrome_options)

print(
    f"Driver established. Initializing connection layer for {len(raw_patent_list)} documents..."
)

try:
    # 4. EXPLICITLY INITIALIZE THE CONNECTION OBJECT (No context 'with' block)
    # Pass your selenium engine straight into the pypatent initializer
    conn = pypatent.WebConnection(use_selenium=True, selenium_driver=driver)

    for raw_id in raw_patent_list:
        # Strip all formatting layout punctuation strings completely
        clean_id = (
            str(raw_id)
            .replace("-", "")
            .replace(",", "")
            .replace("/", "")
            .replace(" ", "")
            .strip()
        )

        try:
            print(f"Scraping deep full-text sections for: {clean_id}")

            # The library requires the web_connection argument to execute properly
            patent_obj = pypatent.Patent.from_patent_number(
                clean_id, web_connection=conn
            )

            # 5. SECURE STRUCTURAL ATTRIBUTES
            title = getattr(patent_obj, "title", "")
            abstract = getattr(patent_obj, "abstract", "")
            claims = getattr(patent_obj, "claims", "")  # Raw complete claims text block
            description = getattr(
                patent_obj, "description", ""
            )  # Multi-paragraph description spec block

            full_text_payload = (
                f"PATENT ID: {clean_id}\n"
                f"TITLE: {title}\n\n"
                f"--- ABSTRACT ---\n{abstract}\n\n"
                f"--- CLAIMS ---\n{claims}\n\n"
                f"--- DESCRIPTION ---\n{description}\n"
            )

            if claims or description:
                file_path = f"./pypatent_fulltext_corpus/{clean_id}.txt"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(full_text_payload)
                print(f"Success: Full text stored for {clean_id}")
            else:
                print(
                    f"Warning: Processing succeeded but page text returned empty for {clean_id}"
                )

            # Maintain a 3-second buffer to mimic realistic page viewing patterns
            time.sleep(3.0)

        except Exception as inner_e:
            print(
                f"Failed to parse document elements for {clean_id}. Details: {inner_e}"
            )

finally:
    # 6. SAFELY KILL BROWSER PROCESS (Manual cleanup phase)
    # Because 'with' isn't running, we must manually quit the driver process or Chrome will hang in memory
    print("Shutting down background browser engine process...")
    driver.quit()

print("\n--- Process Loop Concluded ---")
