import os
import re
import subprocess
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from transformers import AutoTokenizer

PDF_DIR    = "../data/raw/vendors_manuals_pdf"

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

FORM_FEED = "\x0c"  # pdftotext page-break character

# Lines that are just decorative separators: ---- ==== ____ **** ~~~~ #### etc.
SEPARATOR_RE = re.compile(r"^[\s\-_=~*#•·.]{3,}$")

# Page-number-ish lines: "3", "Page 3", "3 / 20", "- 3 -", "3 of 20"
PAGE_NUM_RE = re.compile(
    r"^(page\s*)?\(?\s*\d{1,4}\s*\)?"
    r"(\s*(/|of|-)\s*\d{1,4})?\s*$",
    re.IGNORECASE,
)

COPYRIGHT_RE = re.compile(r"^(©|\(c\)|copyright)\s*\d{0,4}", re.IGNORECASE)
URL_LINE_RE  = re.compile(r"^(www\.|https?://)", re.IGNORECASE)

# Control / non-printable characters (keep tab + newline, drop the rest),
# plus the unicode replacement char and private-use-area junk OCR sometimes emits.
CONTROL_CHARS_RE = re.compile(
    r"[\x00-\x08\x0b\x0e-\x1f\x7f\ufffd\ue000-\uf8ff]"
)

MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")

# Dot-leader runs: "....." or ". . . . ." — whether they fill the whole line
# (TOC separator rows) or sit inline before a page number ("Section 2 .... 12").
DOT_LEADER_RE = re.compile(r"(?:\.\s*){3,}")


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
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {result.stderr}")
    return result.stdout


def _is_symbol_noise(line: str) -> bool:
    """True if the line is mostly punctuation/symbols rather than real words
    (e.g. table-border artifacts, OCR garbage like '| ▪ ▪ —')."""
    letters_digits = sum(ch.isalnum() for ch in line)
    return letters_digits < max(3, int(len(line) * 0.3))


def _strip_control_chars(text: str) -> str:
    text = text.replace("\ufeff", "")  # BOM
    text = CONTROL_CHARS_RE.sub("", text)
    # normalize a few common ligature/bullet artifacts from PDF fonts
    replacements = {
        "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl",
        "\ufb03": "ffi", "\ufb04": "ffl",
        "\u2022": "-", "\u25aa": "-", "\u25cf": "-",
        "\u2013": "-", "\u2014": "-",
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def _find_repeated_boilerplate(pages: list[str], edge_lines: int = 3,
                                min_ratio: float = 0.4) -> set[str]:
    """Find lines that recur near the top/bottom of many pages — running
    headers/footers, repeated document titles, repeated author names, etc.
    These are dropped from every page. Only meaningful when there are
    multiple pages to compare."""
    if len(pages) < 3:
        return set()

    counter = Counter()
    for page in pages:
        raw_lines = [l.strip() for l in page.split("\n") if l.strip()]
        if not raw_lines:
            continue
        edge_candidates = set(raw_lines[:edge_lines] + raw_lines[-edge_lines:])
        for line in edge_candidates:
            # ignore short/numeric lines here, those are handled separately
            if len(line) < 4:
                continue
            counter[line] += 1

    threshold = max(2, int(len(pages) * min_ratio))
    return {line for line, count in counter.items() if count >= threshold}


def clean_pdf_text(raw_text: str, robot_name: str) -> str:
    # split on the page-break char first, THEN strip control chars per page —
    # otherwise the form-feed gets deleted before we can split on it.
    pages = [_strip_control_chars(p) for p in raw_text.split(FORM_FEED)]
    boilerplate = _find_repeated_boilerplate(pages)

    cleaned = []
    prev_line = None
    for page in pages:
        for line in page.split("\n"):
            line = DOT_LEADER_RE.sub(" ", line)
            line = MULTI_SPACE_RE.sub(" ", line.strip())

            if not line or len(line) < 3:
                continue
            if line in boilerplate:
                continue
            if PAGE_NUM_RE.match(line):
                continue
            if SEPARATOR_RE.match(line):
                continue
            if COPYRIGHT_RE.match(line):
                continue
            if URL_LINE_RE.match(line):
                continue
            if _is_symbol_noise(line):
                continue
            if line == prev_line:  # collapse immediate duplicate lines
                continue

            cleaned.append(line)
            prev_line = line

    body = "".join(cleaned)
    return f"[ROBOT:{robot_name}]\n{body}"


# ── Main ──────────────────────────────────────────────────────────────────────

def process_all_pdfs(pdf_dir: str, output_jsonl: str):
    tokenizer = load_tokenizer()

    pdf_files = [f for f in os.listdir(pdf_dir) if f.endswith(".pdf")]
    print(f"Found {len(pdf_files)} PDF files in {pdf_dir}\n")

    records = []
    for filename in pdf_files:
        pdf_path   = os.path.join(pdf_dir, filename)
        robot_name = detect_robot_name(filename)
        print(f"Processing: {filename} -> {robot_name}")

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
                "collected_at": datetime.now(timezone.utc).isoformat(),
            }
            records.append(record)
            print(f"  OK - {n_tokens} tokens")

        except Exception as e:
            print(f"  Failed: {e}")

    with open(output_jsonl, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\nDone - {len(records)} records written -> {output_jsonl}")


if __name__ == "__main__":
    process_all_pdfs(PDF_DIR, "../data/clean/cat3/Cat3data_pdf.jsonl")