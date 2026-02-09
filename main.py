import os
import re
import pandas as pd
import pytesseract
import pdfplumber
from PIL import Image

# ================= HINDI TO ENGLISH =================
from googletrans import Translator
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

translator = Translator()
DEVANAGARI_REGEX = re.compile(r"[\u0900-\u097F]")

def is_hindi(text):
    if not isinstance(text, str):
        return False
    return bool(DEVANAGARI_REGEX.search(text))

def transliterate_hindi(text):
    try:
        return transliterate(text, sanscript.DEVANAGARI, sanscript.ITRANS).title()
    except Exception:
        return text

def translate_hindi(text):
    try:
        translated = translator.translate(text, src="hi", dest="en").text

        # 🔥 If translation still contains Hindi → transliterate
        if is_hindi(translated):
            return transliterate_hindi(text)

        return translated

    except Exception:
        return transliterate_hindi(text)

def translate_hindi_df(df):
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(
                lambda x: translate_hindi(x) if is_hindi(x) else x
            )
    return df

# ================= PATH SETUP =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
PINCODE_FILE = os.path.join(BASE_DIR, "allStateData.csv")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Uncomment if needed
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# ================= LOAD PINCODE MASTER =================
pin_df = pd.read_csv(PINCODE_FILE, header=None, dtype=str)

PIN_COL = 4
DIST_COL = 7
STATE_COL = 8

pin_df = pin_df[[PIN_COL, DIST_COL, STATE_COL]]
pin_df.columns = ["pincode", "district", "state"]

pin_df["pincode"] = pin_df["pincode"].astype(str).str.strip()
pin_df = pin_df[pin_df["pincode"].str.isdigit() & (pin_df["pincode"].str.len() == 6)]
pin_df = pin_df.drop_duplicates(subset="pincode", keep="first")

PINCODE_LOOKUP = pin_df.set_index("pincode")[["state", "district"]].to_dict("index")

print(f"✔ Loaded {len(PINCODE_LOOKUP)} pincodes")

# ================= PHONE NORMALIZATION =================
def normalize_phone(val):
    if val is None:
        return ""
    digits = re.sub(r"\D", "", str(val))
    if len(digits) >= 10:
        return digits[-10:]
    return ""

# ================= PINCODE CLEAN =================
def clean_pincode(val):
    if val is None:
        return ""
    val = str(val).strip()
    return val if val.isdigit() and len(val) == 6 else ""

# ================= CLEAN DATAFRAME =================
def clean_dataframe(df):
    df = df.copy()

    col_map = {c: re.sub(r"[^a-z0-9]", "", c.lower()) for c in df.columns}

    # 🔥 DROP CITY COLUMN COMPLETELY
    for col, cname in col_map.items():
        if cname.startswith("city"):
            df.drop(columns=[col], inplace=True)
            break

    # 📞 PHONE NORMALIZATION
    for col, cname in col_map.items():
        if "phone" in cname or "mobile" in cname:
            df[col] = df[col].apply(normalize_phone)

    # 📍 PINCODE → STATE & DISTRICT
    pin_cols = [c for c, cname in col_map.items() if "pin" in cname]
    if not pin_cols:
        return df

    pcol = pin_cols[0]
    df[pcol] = df[pcol].apply(clean_pincode)

    df["State"] = ""
    df["District"] = ""

    for i, pin in df[pcol].items():
        if pin in PINCODE_LOOKUP:
            df.at[i, "State"] = PINCODE_LOOKUP[pin]["state"]
            df.at[i, "District"] = PINCODE_LOOKUP[pin]["district"]

    return df

# ================= PDF TABLE TO DF =================
def pdf_to_df(path):
    tables = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                tables.append(pd.DataFrame(table[1:], columns=table[0]))
    return pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()

# ================= IMAGE TABLE TO DF =================
def image_to_df(path):
    data = pytesseract.image_to_data(
        Image.open(path),
        output_type=pytesseract.Output.DATAFRAME
    )
    data = data.dropna(subset=["text"])

    rows = {}
    for _, row in data.iterrows():
        key = (row["block_num"], row["line_num"])
        rows.setdefault(key, []).append(row["text"])

    table = [" ".join(v) for v in rows.values()]
    return pd.DataFrame({"pincode": table})

# ================= MAIN PROCESS =================
def process_files():
    for file in os.listdir(INPUT_DIR):
        path = os.path.join(INPUT_DIR, file)

        try:
            if file.lower().endswith(".xlsx"):
                print(f"Processing Excel: {file}")
                df = pd.read_excel(path)

            elif file.lower().endswith(".pdf"):
                print(f"Processing PDF: {file}")
                df = pdf_to_df(path)

            elif file.lower().endswith((".jpg", ".jpeg", ".png")):
                print(f"Processing Image: {file}")
                df = image_to_df(path)

            else:
                continue

            if df.empty:
                print("⚠ No table found")
                continue

            df = clean_dataframe(df)

            # 🔥 Hindi → English (translation + transliteration fallback)
            df = translate_hindi_df(df)

            df.drop_duplicates(inplace=True)

            output_path = os.path.join(
                OUTPUT_DIR, f"cleaned_{os.path.splitext(file)[0]}.xlsx"
            )
            df.to_excel(output_path, index=False)

            print(f"✅ Saved: {output_path}")

        except Exception as e:
            print(f"❌ Failed {file}: {e}")

# ================= RUN =================
if __name__ == "__main__":
    process_files()
















# import os
# import re
# import pandas as pd
# import pytesseract
# import pdfplumber
# from PIL import Image

# # ================= PATH SETUP =================
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# INPUT_DIR = os.path.join(BASE_DIR, "input")
# OUTPUT_DIR = os.path.join(BASE_DIR, "output")
# PINCODE_FILE = os.path.join(BASE_DIR, "allStateData.csv")

# os.makedirs(OUTPUT_DIR, exist_ok=True)

# # Uncomment if needed
# # pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# # ================= LOAD PINCODE MASTER =================
# pin_df = pd.read_csv(PINCODE_FILE, header=None, dtype=str)

# # Fixed structure of your CSV
# PIN_COL = 4
# DIST_COL = 7
# STATE_COL = 8

# pin_df = pin_df[[PIN_COL, DIST_COL, STATE_COL]]
# pin_df.columns = ["pincode", "district", "state"]

# pin_df["pincode"] = pin_df["pincode"].astype(str).str.strip()
# pin_df = pin_df[pin_df["pincode"].str.isdigit() & (pin_df["pincode"].str.len() == 6)]
# pin_df = pin_df.drop_duplicates(subset="pincode", keep="first")

# PINCODE_LOOKUP = pin_df.set_index("pincode")[["state", "district"]].to_dict("index")

# print(f"✔ Loaded {len(PINCODE_LOOKUP)} pincodes")

# # ================= PHONE NORMALIZATION =================
# def normalize_phone(val):
#     if val is None:
#         return ""
#     digits = re.sub(r"\D", "", str(val))
#     if len(digits) >= 10:
#         return digits[-10:]
#     return ""

# # ================= PINCODE CLEAN =================
# def clean_pincode(val):
#     if val is None:
#         return ""
#     val = str(val).strip()
#     return val if val.isdigit() and len(val) == 6 else ""

# # ================= CLEAN DATAFRAME =================
# def clean_dataframe(df):
#     df = df.copy()

#     # Normalize column names (for detection only)
#     col_map = {c: re.sub(r"[^a-z0-9]", "", c.lower()) for c in df.columns}

#     # 🔥 DROP CITY COLUMN COMPLETELY
#     for col, cname in col_map.items():
#         if cname.startswith("city"):
#             df.drop(columns=[col], inplace=True)
#             break

#     # 📞 PHONE NORMALIZATION
#     for col, cname in col_map.items():
#         if "phone" in cname or "mobile" in cname:
#             df[col] = df[col].apply(normalize_phone)

#     # 📍 PINCODE → STATE & DISTRICT
#     pin_cols = [c for c, cname in col_map.items() if "pin" in cname]
#     if not pin_cols:
#         return df

#     pcol = pin_cols[0]
#     df[pcol] = df[pcol].apply(clean_pincode)

#     df["State"] = ""
#     df["District"] = ""

#     for i, pin in df[pcol].items():
#         if pin in PINCODE_LOOKUP:
#             df.at[i, "State"] = PINCODE_LOOKUP[pin]["state"]
#             df.at[i, "District"] = PINCODE_LOOKUP[pin]["district"]

#     return df

# # ================= PDF TABLE TO DF =================
# def pdf_to_df(path):
#     tables = []
#     with pdfplumber.open(path) as pdf:
#         for page in pdf.pages:
#             table = page.extract_table()
#             if table:
#                 tables.append(pd.DataFrame(table[1:], columns=table[0]))
#     return pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()

# # ================= IMAGE TABLE TO DF =================
# def image_to_df(path):
#     data = pytesseract.image_to_data(
#         Image.open(path),
#         output_type=pytesseract.Output.DATAFRAME
#     )
#     data = data.dropna(subset=["text"])

#     rows = {}
#     for _, row in data.iterrows():
#         key = (row["block_num"], row["line_num"])
#         rows.setdefault(key, []).append(row["text"])

#     table = [" ".join(v) for v in rows.values()]
#     return pd.DataFrame({"pincode": table})

# # ================= MAIN PROCESS =================
# def process_files():
#     for file in os.listdir(INPUT_DIR):
#         path = os.path.join(INPUT_DIR, file)

#         try:
#             if file.lower().endswith(".xlsx"):
#                 print(f"Processing Excel: {file}")
#                 df = pd.read_excel(path)

#             elif file.lower().endswith(".pdf"):
#                 print(f"Processing PDF: {file}")
#                 df = pdf_to_df(path)

#             elif file.lower().endswith((".jpg", ".jpeg", ".png")):
#                 print(f"Processing Image: {file}")
#                 df = image_to_df(path)

#             else:
#                 continue

#             if df.empty:
#                 print("⚠ No table found")
#                 continue

#             df = clean_dataframe(df)
#             df.drop_duplicates(inplace=True)

#             output_path = os.path.join(
#                 OUTPUT_DIR, f"cleaned_{os.path.splitext(file)[0]}.xlsx"
#             )
#             df.to_excel(output_path, index=False)

#             print(f"✅ Saved: {output_path}")

#         except Exception as e:
#             print(f"❌ Failed {file}: {e}")

# # ================= RUN =================
# if __name__ == "__main__":
#     process_files()


