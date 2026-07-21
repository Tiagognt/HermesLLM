"""
Entry point for PHASE 2 (transformation) -- category 1.

Reads the phase-1 raw files and produces `corpus_clean.jsonl` +
`corpus_stats.md`. The chain, in this order:

  1. adaptation      files -> DocCandidate (text_adapters)
  2. scrubbing       secret removal (common.secret_scrubber)
  3. contamination   overlap with the evaluation scenario
  4. deduplication   exact then near-exact (common.dedup)
  5. counting        Qwen3 tokens
  6. quotas          per-source cap, selection spread over the subtrees
  7. assembly        DocumentDraft -> JSONL record (tier A)

The order is not arbitrary: deduplicating BEFORE applying the quotas
guarantees the budget is spent on unique content, rather than wasted on
duplicates that would be removed afterwards.

Adjusting the size of cat1 requires NO re-collection: change `token_budget`
in sources.py (or pass --budget-scale) and re-run.

Runnable from any directory:
    python3 /path/to/src/cat1/build_corpus.py
    python3 .../build_corpus.py --budget-scale 0.75
    python3 .../build_corpus.py --only ros2_documentation
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> src/

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List

from common import paths
from common.contamination import ContaminationChecker
from common.corpus_assembler import DocumentDraft, assemble_record, validate_record
from common.dedup import DuplicateIndex
from common.quota import select_within_budget
from common.run_report import RunReport
from common.secret_scrubber import scrub
from common.tokenizer_utils import TokenCounter
from cat1 import text_adapters
from cat1.text_adapters import DocCandidate

CATEGORY = "cat1"
TIER = "A"          # tier A in the project taxonomy (see the brief)
METADATA_PATH = paths.metadata_path(CATEGORY)
CORPUS_PATH = paths.corpus_path(CATEGORY)
STATS_PATH = paths.stats_path(CATEGORY)


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------

def write_stats(rows: List[dict], *, skipped: Counter, per_source: Dict[str, dict],
                tc: TokenCounter, contamination_summary: str,
                dedup_desc: str, secrets: Counter, report_path) -> None:
    total_tokens = sum(r["n_tokens"] for r in rows)
    by_family: Counter = Counter()
    by_family_tok: Counter = Counter()
    by_license: Counter = Counter()
    by_kind: Counter = Counter()
    for r in rows:
        by_family[r["family"]] += 1
        by_family_tok[r["family"]] += r["n_tokens"]
        by_license[r["license"]] += 1
        by_kind[r["kind"]] += 1

    lines = ["# Category 1 corpus — statistics", ""]
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Project root: `{paths.PROJECT_ROOT}`")
    lines.append(f"- Tier: {TIER}")
    lines.append(f"- Records: {len(rows)}")
    lines.append(f"- Total tokens: {total_tokens} "
                 f"({'Qwen3 exact' if tc.is_exact else 'APPROXIMATE — ' + tc.describe()})")
    lines.append(f"- Contamination check: {contamination_summary}")
    lines.append(f"- Deduplication: {dedup_desc}")
    if report_path is not None:
        lines.append(f"- Run report: `{paths.to_relative(report_path)}`")
    lines.append("")

    lines.append("## Per source family")
    lines.append("")
    lines.append("| Family | Documents | Tokens | Share |")
    lines.append("|---|---:|---:|---:|")
    for fam in sorted(by_family_tok, key=lambda f: -by_family_tok[f]):
        pct = 100.0 * by_family_tok[fam] / total_tokens if total_tokens else 0
        lines.append(f"| {fam} | {by_family[fam]} | {by_family_tok[fam]:,} | {pct:.1f} % |")
    lines.append("")

    lines.append("## Per source")
    lines.append("")
    lines.append("| Source | Family | Kept | Tokens | Cap | Dropped (quota) |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for sid in sorted(per_source, key=lambda s: -per_source[s]["tokens"]):
        d = per_source[sid]
        lines.append(f"| `{sid}` | {d['family']} | {d['kept']} | {d['tokens']:,} "
                     f"| {d['budget']:,} | {d['over_budget']} |")
    lines.append("")

    lines.append("## Per content nature")
    for k in sorted(by_kind):
        lines.append(f"- {k}: {by_kind[k]} documents")
    lines.append("")

    lines.append("## Per license")
    for lic in sorted(by_license):
        lines.append(f"- {lic}: {by_license[lic]}")
    lines.append("")

    lines.append("## Dropped documents")
    lines.append("")
    lines.append("| Reason | Count |")
    lines.append("|---|---:|")
    for reason, n in skipped.most_common():
        lines.append(f"| {reason} | {n} |")
    lines.append("")

    lines.append("## Masked secrets")
    if secrets:
        for k, v in secrets.most_common():
            lines.append(f"- {k}: {v}")
    else:
        lines.append("- no secret detected in the retained sources")

    STATS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 2 -- build the cat1 corpus")
    ap.add_argument("--only", default=None,
                    help="restrict to these source_ids (comma-separated)")
    ap.add_argument("--budget-scale", type=float, default=1.0,
                    help="multiply every cap (0.75 = corpus 25%% smaller)")
    ap.add_argument("--dedup-threshold", type=float, default=0.85,
                    help="near-duplicate similarity threshold (0 = disabled)")
    args = ap.parse_args()

    report = RunReport("cat1-build-corpus", category=CATEGORY,
                       title="Category 1 — phase 2 (corpus build)")

    if not METADATA_PATH.exists():
        raise SystemExit(f"Metadata missing: {METADATA_PATH}\n"
                         f"-> run collect_docs.py first")

    metas = [json.loads(l) for l in
             METADATA_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        metas = [m for m in metas if m["source_id"] in wanted]

    tc = TokenCounter()
    checker = ContaminationChecker.from_config()
    index = DuplicateIndex(threshold=args.dedup_threshold)

    print(f"Project root  : {paths.PROJECT_ROOT}")
    print(f"Sources       : {len(metas)}")
    print(f"Tokenizer     : {tc.describe()}")
    print(f"Contamination : {checker.describe()}")
    print(f"Deduplication : {index.describe()}")
    print(f"Cap scale     : x{args.budget_scale}\n")
    report.info("Sources", len(metas))
    report.info("Tokenizer", tc.describe())
    report.info("Contamination", checker.describe())
    report.info("Deduplication", index.describe())
    report.info("Cap scale", f"x{args.budget_scale}")

    skipped: Counter = Counter()
    secrets: Counter = Counter()
    per_source: Dict[str, dict] = {}
    all_kept: List[tuple] = []      # (meta, DocCandidate)

    for meta in metas:
        sid = meta["source_id"]
        root = paths.from_relative(meta["raw_dir"])
        if not root.exists():
            report.fail(sid, kind=meta["kind"],
                        reason=f"raw directory missing: {root} — re-run phase 1")
            continue

        try:
            candidates = text_adapters.adapt(meta, root)
        except Exception as exc:  # a broken source does not stop the run
            report.fail(sid, kind=meta["kind"], exc=exc)
            continue

        n_raw = len(candidates)
        surviving: List[DocCandidate] = []
        for c in candidates:
            # -- secrets: masked before anything else, so no sensitive value
            #    ever transits through the deduplication indexes.
            res = scrub(c.text)
            if res.n_redacted:
                for k, v in res.counts.items():
                    secrets[k] += v
                c.text = res.text
                c.flags["scrubbed"] = res.describe()

            verdict = checker.check(c.text)
            if verdict.is_contaminated:
                skipped["contamination"] += 1
                report.skip(c.doc_id, kind=meta["kind"],
                            reason=f"CONTAMINATION — {verdict.describe()}")
                continue

            if args.dedup_threshold > 0:
                dup = index.check(c.text)
                if dup.is_duplicate:
                    skipped[f"{dup.kind} duplicate"] += 1
                    continue
                index.add(c.doc_id, c.text)

            c.n_tokens = tc.count(c.text)
            surviving.append(c)

        budget = int(meta["token_budget"] * args.budget_scale)
        kept, dropped = select_within_budget(surviving, budget)
        skipped["over quota"] += len(dropped)

        per_source[sid] = {
            "family": meta["family"], "kept": len(kept),
            "tokens": sum(c.n_tokens for c in kept),
            "budget": budget, "over_budget": len(dropped),
        }
        all_kept.extend((meta, c) for c in kept)

        print(f"  [{sid:26s}] {n_raw:4d} candidates -> {len(surviving):4d} unique "
              f"-> {len(kept):4d} kept ({per_source[sid]['tokens']:,} tokens)")
        report.ok(sid, kind=meta["kind"],
                  detail=f"{n_raw} candidates, {len(surviving)} unique, "
                         f"{len(kept)} kept, {per_source[sid]['tokens']:,} tokens "
                         f"(cap {budget:,})")

    # ---- writing ---------------------------------------------------------
    paths.ensure_dirs(CORPUS_PATH.parent)
    rows: List[dict] = []
    with CORPUS_PATH.open("w", encoding="utf-8") as f:
        for meta, c in all_kept:
            draft = DocumentDraft(
                robot_id=c.doc_id, source_type=c.kind, text=c.text,
                license_status=meta["license_status"], url=meta.get("url", ""),
                lang="en", source_name=meta["source_id"],
            )
            extra = {
                "family": c.family,
                "kind": c.kind,
                "rel_path": c.rel_path,
                "repo_url": meta["repo_url"],
                "repo_commit": meta["repo_commit"],
            }
            # Part index for split documents, trace of the scrubbing: what
            # was done to the text must be readable in the corpus.
            if "part" in c.flags:
                extra["part"] = int(c.flags["part"])
                extra["n_parts"] = int(c.flags["n_parts"])
            if "scrubbed" in c.flags:
                extra["scrubbed"] = c.flags["scrubbed"]
            rec = assemble_record(
                draft, category=CATEGORY, tier=TIER, token_counter=tc,
                doc_id=c.doc_id, extra=extra,
            )
            rec["n_tokens"] = c.n_tokens        # already counted, do not recount
            validate_record(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows.append(rec)

    total_tokens = sum(r["n_tokens"] for r in rows)
    contamination_summary = (
        "PASSED — 0 overlap" if not skipped["contamination"]
        else f"{skipped['contamination']} document(s) excluded"
    ) + f" ({checker.describe()})"
    dedup_desc = (f"{skipped['exact duplicate']} exact duplicates, "
                  f"{skipped['near duplicate']} near-duplicates removed "
                  f"({index.describe()})")

    report.info("Contamination result", contamination_summary)
    report.info("Deduplication result", dedup_desc)
    report.info("Tokens kept", f"{total_tokens:,}")
    report_path = report.write()

    write_stats(rows, skipped=skipped, per_source=per_source, tc=tc,
                contamination_summary=contamination_summary,
                dedup_desc=dedup_desc, secrets=secrets, report_path=report_path)

    print(f"\nCorpus written: {CORPUS_PATH}")
    print(f"  {len(rows)} records, {total_tokens:,} tokens (tier {TIER})")
    print(f"  contamination : {contamination_summary}")
    print(f"  deduplication : {dedup_desc}")
    if secrets:
        print(f"  secrets masked : {dict(secrets)}")
    print(f"  report : {report_path}")


if __name__ == "__main__":
    main()
