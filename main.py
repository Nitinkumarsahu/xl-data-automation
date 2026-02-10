import os
import re
from pathlib import Path

import pandas as pd
import pdfplumber
import pytesseract
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

        # If translation still contains Hindi, transliterate fallback.
        if is_hindi(translated):
            return transliterate_hindi(text)

        return translated

    except Exception:
        return transliterate_hindi(text)


def translate_hindi_df(df):
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(lambda x: translate_hindi(x) if is_hindi(x) else x)
    return df


# ================= PATH SETUP =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
PINCODE_FILE = os.path.join(BASE_DIR, "allStateData.csv")

os.makedirs(INPUT_DIR, exist_ok=True)
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

    # Drop city column completely.
    for col, cname in col_map.items():
        if cname.startswith("city"):
            df.drop(columns=[col], inplace=True)
            break

    # Phone normalization.
    for col, cname in col_map.items():
        if "phone" in cname or "mobile" in cname:
            df[col] = df[col].apply(normalize_phone)

    # Pincode -> State & District
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
    data = pytesseract.image_to_data(Image.open(path), output_type=pytesseract.Output.DATAFRAME)
    data = data.dropna(subset=["text"])

    rows = {}
    for _, row in data.iterrows():
        key = (row["block_num"], row["line_num"])
        rows.setdefault(key, []).append(row["text"])

    table = [" ".join(v) for v in rows.values()]
    return pd.DataFrame({"pincode": table})


SUPPORTED_EXTENSIONS = {".xlsx", ".pdf", ".jpg", ".jpeg", ".png"}


# ================= SINGLE FILE PROCESS =================
def process_file(source_path, output_dir=OUTPUT_DIR):
    source_path = Path(source_path)
    suffix = source_path.suffix.lower()

    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix}")

    if suffix == ".xlsx":
        df = pd.read_excel(source_path)
    elif suffix == ".pdf":
        df = pdf_to_df(source_path)
    else:
        df = image_to_df(source_path)

    if df.empty:
        raise ValueError("No table found in file")

    df = clean_dataframe(df)
    df = translate_hindi_df(df)
    df.drop_duplicates(inplace=True)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"cleaned_{source_path.stem}.xlsx"
    df.to_excel(output_path, index=False)

    return str(output_path)


# ================= MAIN PROCESS =================
def process_files(input_dir=INPUT_DIR, output_dir=OUTPUT_DIR):
    for file in os.listdir(input_dir):
        path = os.path.join(input_dir, file)

        try:
            if Path(file).suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            print(f"Processing: {file}")
            output_path = process_file(path, output_dir=output_dir)
            print(f"✅ Saved: {output_path}")

        except Exception as e:
            print(f"❌ Failed {file}: {e}")


# ================= RUN =================
if __name__ == "__main__":
    process_files()
