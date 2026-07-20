"""
Point d'entrée de la phase 2 (transformation) -- catégorie 3.

Lit les bruts de la phase 1 (URDF collectés + manuels PDF déposés
manuellement), applique la barrière licence, produit un corpus JSONL
unifié (1 enregistrement par source) + des statistiques.

    python3 build_corpus.py                         # URDF seuls, gabarit (hors ligne)
    python3 build_corpus.py --provider anthropic    # descriptions via Claude
    python3 build_corpus.py --sources urdf,pdf --allow-proprietary-pdf
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from license_utils import classify_license, is_collectible
from llm_provider import get_provider
from tokenizer_utils import TokenCounter
from corpus_assembler import assemble_record, validate_record
import urdf_adapter
import pdf_adapter

METADATA_PATH = Path("../../data/cat3/collection_metadata.jsonl")
MANUALS_DIR = Path("../../data/cat3/manuals")
MANIFEST_PATH = Path(__file__).with_name("pdf_manifest.json")
OUT_DIR = Path("../../data/cat3/clean")
CORPUS_PATH = OUT_DIR / "corpus_clean.jsonl"
STATS_PATH = OUT_DIR / "corpus_stats.md"

ALLOW_NO_LICENSE_FOR = {"agilex_ranger_mini_v3"}


def _iter_urdf(provider, records: list, excluded: list):
    if not METADATA_PATH.exists():
        return
    for line in METADATA_PATH.read_text(encoding="utf-8").splitlines():
        meta = json.loads(line)
        rid = meta["robot_id"]
        status = meta["license_status"]
        override = rid in ALLOW_NO_LICENSE_FOR
        if not is_collectible(status, allow_no_license_override=override):
            excluded.append((rid, "urdf", status))
            continue
        urdf_path = Path(meta["raw_urdf_path"])
        if not urdf_path.is_absolute():
            urdf_path = METADATA_PATH.parent / Path(*urdf_path.parts[urdf_path.parts.index("raw"):]) \
                if "raw" in urdf_path.parts else urdf_path
        try:
            draft = urdf_adapter.adapt(
                rid, urdf_path,
                license_status=status,
                url=meta.get("repo_url", ""),
                source_name=meta.get("source_type", "robot_descriptions"),
                provider=provider,
            )
            records.append(draft)
        except Exception as exc:  # un URDF cassé ne doit pas arrêter le run
            print(f"[{rid}] ECHEC voie URDF : {exc}")


def _iter_pdf(provider, records: list, excluded: list, *, allow_proprietary: bool, llm_format: bool):
    if not MANIFEST_PATH.exists():
        return
    manuals = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["manuals"]
    for m in manuals:
        rid = m["robot_id"]
        pdf_path = MANUALS_DIR / rid / m["target_filename"]
        if not pdf_path.exists():
            continue  # manuel non téléchargé -> on ignore silencieusement
        status = classify_license(m.get("license_spdx"))
        if not is_collectible(status, allow_no_license_override=allow_proprietary):
            excluded.append((rid, "pdf_manual", status))
            continue
        try:
            draft = pdf_adapter.adapt(
                rid, pdf_path,
                license_status=status,
                url=m.get("url", ""),
                source_name=f"manual:{rid}",
                provider=provider,
                use_llm_format=llm_format,
            )
            records.append(draft)
        except Exception as exc:  # PDF corrompu/protégé -> on journalise et on continue
            print(f"[{rid}] ECHEC voie PDF : {exc}")


def write_stats(rows: list, excluded: list, tc: TokenCounter) -> None:
    by_type = Counter(r["source_type"] for r in rows)
    tokens_by_type = Counter()
    for r in rows:
        tokens_by_type[r["source_type"]] += r["n_tokens"]
    total_tokens = sum(r["n_tokens"] for r in rows)

    lines = ["# Corpus catégorie 3 — statistiques", ""]
    lines.append(f"- Généré le : {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Enregistrements : {len(rows)}")
    lines.append(f"- Tokens totaux : {total_tokens} "
                 f"({'Qwen3 exact' if tc.is_exact else 'APPROXIMATIF — ' + tc.describe()})")
    lines.append("")
    lines.append("## Par type de source")
    for t in sorted(by_type):
        lines.append(f"- {t} : {by_type[t]} enregistrements, {tokens_by_type[t]} tokens")
    if excluded:
        lines.append("")
        lines.append("## Exclus par la barrière licence")
        for rid, st, status in excluded:
            lines.append(f"- {rid} ({st}) : {status}")
    STATS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=None, help="anthropic|openai|gemini|template")
    ap.add_argument("--sources", default="urdf", help="urdf,pdf (séparés par des virgules)")
    ap.add_argument("--allow-proprietary-pdf", action="store_true",
                    help="inclure les manuels sans licence conforme (décision explicite)")
    ap.add_argument("--llm-format-pdf", action="store_true",
                    help="passer les manuels par le LLM pour mise en forme (extractif)")
    args = ap.parse_args()

    provider = get_provider(args.provider)
    tc = TokenCounter()
    sources = {s.strip() for s in args.sources.split(",")}

    drafts, excluded = [], []
    if "urdf" in sources:
        _iter_urdf(provider, drafts, excluded)
    if "pdf" in sources:
        _iter_pdf(provider, drafts, excluded,
                  allow_proprietary=args.allow_proprietary_pdf,
                  llm_format=args.llm_format_pdf)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    with CORPUS_PATH.open("w", encoding="utf-8") as f:
        for draft in drafts:
            rec = assemble_record(draft, token_counter=tc)
            validate_record(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows.append(rec)

    write_stats(rows, excluded, tc)
    print(f"Corpus écrit : {CORPUS_PATH} ({len(rows)} enregistrements)")
    print(f"Provider LLM : {provider.name} | tokenizer : {tc.describe()}")
    if excluded:
        print(f"Exclus (licence) : {len(excluded)} -> voir {STATS_PATH}")


if __name__ == "__main__":
    main()
