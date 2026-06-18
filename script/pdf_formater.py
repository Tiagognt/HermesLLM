import os
import re
import subprocess
import json
import uuid
from datetime import datetime, timezone
from transformers import AutoTokenizer

PDF_DIR    = "../data/vendors_manuals_pdf"

ROBOT_NAME_MAP = {
    "g1":           "Unitree G1",
    "go2":          "Unitree Go2",
    "ranger":       "AgileX Ranger Mini",
    "scout":        "AgileX Scout",
    "husky":        "Clearpath Husky A200",
    "spot":         "Boston Dynamics Spot",
    "h1":           "Unitree H1",
    "b2":           "Unitree B2",
    "stretch":      "Hello Robot Stretch",
    "ur10":         "Universal Robots UR10e",
    "franka":       "Franka Research 3",
    "fr3":          "Franka Research 3",
}

# ── Tokenizer ─────────────────────────────────────────────────────────────────

def load_tokenizer():
    try:
        tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-0.6B", trust_remote_code=True)
        print("Qwen3 tokenizer loaded")
        return tok
    except Exception as e:
        print(f"Tokenizer unavailable ({e}), falling back to char/4 estimate")
        return None

def count_tokens(text: str, tokenizer) -> int:
    if tokenizer is not None:
        return len(tokenizer.encode(text))
    return max(1, len(text) // 4)

# ── PDF processing ────────────────────────────────────────────────────────────

def detect_robot_name(filename: str) -> str:
    filename_lower = filename.lower()
    for keyword, name in ROBOT_NAME_MAP.items():
        if keyword in filename_lower:
            return name
    return os.path.splitext(filename)[0]

def pdf_to_text(pdf_path: str) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", pdf_path, "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {result.stderr}")
    return result.stdout

def clean_pdf_text(raw_text: str, robot_name: str) -> str:
    lines = raw_text.split("\n")
    cleaned = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if re.match(r"^(page\s*)?\d+\s*$", line, re.IGNORECASE):
            continue
        if re.match(r"^©\s*\d{4}", line):
            continue
        if re.match(r"^www\.", line):
            continue
        if len(line) < 5:
            continue
        cleaned.append(line)
    return f"[ROBOT:{robot_name}]\n" + "".join(cleaned)

# ── Main ──────────────────────────────────────────────────────────────────────

def process_all_pdfs(pdf_dir: str, output_jsonl: str):
    tokenizer = load_tokenizer()

    pdf_files = [f for f in os.listdir(pdf_dir) if f.endswith(".pdf")]
    print(f"Found {len(pdf_files)} PDF files in {pdf_dir}\n")

    records = []
    for filename in pdf_files:
        pdf_path   = os.path.join(pdf_dir, filename)
        robot_name = detect_robot_name(filename)
        print(f"Processing: {filename} → {robot_name}")

        try:
            raw_text   = pdf_to_text(pdf_path)
            clean_text = clean_pdf_text(raw_text, robot_name)
            n_tokens   = count_tokens(clean_text, tokenizer)

            record = {
                "id":           str(uuid.uuid4()),
                "source":       filename,
                "category":     3,
                "tier":         "D",
                "license":      "internal-training-only",
                "url":          pdf_path,
                "lang":         "en",
                "text":         clean_text,
                "n_tokens":     n_tokens,
                "collected_at": datetime.now(timezone.utc).isoformat()
            }
            records.append(record)
            print(f"  OK — {n_tokens} tokens")

        except Exception as e:
            print(f"  Failed: {e}")

    with open(output_jsonl, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\nDone — {len(records)} records written → {output_jsonl}")


if __name__ == "__main__":
    process_all_pdfs(PDF_DIR, "../data/Cat3data_pdf.jsonl")