import json
import uuid
from datetime import datetime, timezone
from transformers import AutoTokenizer
import urdf_parser as prs

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



# Then build your JSONL record normally

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":

    tokenizer = load_tokenizer()
    records = []

    # repo_texts is built by parser.py at import time
    # structure: { "owner/repo": [(text, license, url), ...] }
    for repo_name, entries in prs.repo_texts.items():
        print(f"\nBuilding records for {repo_name} — {len(entries)} files")

        for text, license, url in entries:
            record = {
                "id":           str(uuid.uuid4()),
                "source":       repo_name,
                "category":     3,
                "tier":         "D",
                "license":      license,
                "url":          url,
                "lang":         "en",
                "text":         text,
                "n_tokens":     count_tokens(text, tokenizer),
                "collected_at": datetime.now(timezone.utc).isoformat()
            }
            records.append(record)
            print(f"  {url.split('/')[-1]} — {record['n_tokens']} tokens")

    output_path = "../data/Cat3data_urdf.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\nDone — {len(records)} records written → {output_path}")
    
