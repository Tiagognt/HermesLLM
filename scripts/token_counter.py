import json
import sys
import os

PATHS = ["../data/clean/cat1/", "../data/clean/cat2/", "../data/clean/cat3/"]

files = []
for path in PATHS:
    files.append([f for f in os.listdir(path) if f.endswith(".jsonl")])

def count_total_tokens(jsonl_path: str) -> int:
    total = 0
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                total += record.get("n_tokens", 0)
            except json.JSONDecodeError:
                continue
    return total

if __name__ == "__main__":
    total_tokens = []
    for i in range(len(PATHS)):
        cat_tokens = 0
        for file in files[i]:
            jsonl_path = os.path.join(PATHS[i], file)
            cat_tokens += count_total_tokens(jsonl_path)
        total_tokens.append(cat_tokens)
        print(f"{len(files[i])} files for Category {i+1} | Token amount: {cat_tokens} tokens")




    print(f"Total tokens across all categories: {sum(total_tokens)} tokens\n")

    proportions = [tokens / sum(total_tokens) for tokens in total_tokens]
    for i, proportion in enumerate(proportions):
        print(f"Category {i+1} proportion: {proportion:.2%}")