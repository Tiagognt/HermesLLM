"""
Merge the three categories into a single corpus -- final deliverable.

The per-category corpora remain the SOURCE OF TRUTH: this module never
modifies them, it produces a regenerable derivative in `data/full/`. Any
correction is made in the category concerned, then the merge is re-run.

The merge is not a plain concatenation. It applies the checks that no
single category can perform on its own:

  1. identifier uniqueness ACROSS categories;
  2. CROSS-category deduplication -- cat1 and cat2 both draw from the ROS
     ecosystem, and nothing guaranteed a document would not appear on both
     sides;
  3. contamination, re-run over the assembled corpus (one more belt: each
     category already checked, but the deliverable must be verifiable on
     its own);
  4. verification of the MIX mandated by the brief
     (cat1 60-70% · cat2 15-25% · cat3 10-15%), which only means anything
     at this level.

Runnable from any directory:
    python3 /path/to/src/common/merge_corpus.py
    python3 .../merge_corpus.py --shuffle          # deterministic shuffle
    python3 .../merge_corpus.py --no-cross-dedup
"""

from __future__ import annotations

import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

if __name__ == "__main__":  # direct execution: src/ must be on sys.path
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import paths
from common.contamination import ContaminationChecker
from common.corpus_assembler import validate_record
from common.dedup import DuplicateIndex
from common.run_report import RunReport

# Bands mandated by the brief, per category.
TARGET_MIX: Dict[str, Tuple[float, float]] = {
    "cat1": (0.60, 0.70),
    "cat2": (0.15, 0.25),
    "cat3": (0.10, 0.15),
}
SHUFFLE_SEED = 20260721


def load_category(category: str) -> List[dict]:
    path = paths.corpus_path(category)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def check_mix(by_cat_tokens: Counter) -> Tuple[bool, List[str]]:
    total = sum(by_cat_tokens.values())
    lines, ok = [], True
    for cat in ("cat1", "cat2", "cat3"):
        tok = by_cat_tokens.get(cat, 0)
        share = tok / total if total else 0.0
        lo, hi = TARGET_MIX[cat]
        verdict = "OK" if lo <= share <= hi else "OUT OF BAND"
        if verdict != "OK":
            ok = False
        lines.append(f"| {cat} | {tok:,} | {share*100:.1f} % | "
                     f"{lo*100:.0f}–{hi*100:.0f} % | {verdict} |")
    return ok, lines


def write_stats(rows: List[dict], *, by_cat: Counter, by_cat_tokens: Counter,
                mix_ok: bool, mix_lines: List[str], dropped: Counter,
                dedup_desc: str, contamination_summary: str,
                report_path) -> None:
    total_tokens = sum(r["n_tokens"] for r in rows)
    by_tier: Counter = Counter()
    by_license: Counter = Counter()
    by_source_type: Counter = Counter()
    for r in rows:
        by_tier[r["tier"]] += r["n_tokens"]
        by_license[r["license"]] += 1
        by_source_type[r.get("source_type", "?")] += 1

    L = ["# RoboMix full corpus — statistics", ""]
    L.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    L.append(f"- Project root: `{paths.PROJECT_ROOT}`")
    L.append(f"- Records: {len(rows)}")
    L.append(f"- Total tokens: {total_tokens:,} (Qwen3)")
    L.append(f"- Contamination check: {contamination_summary}")
    L.append(f"- Cross-category deduplication: {dedup_desc}")
    if report_path is not None:
        L.append(f"- Run report: `{paths.to_relative(report_path)}`")
    L.append("")

    L.append("## Mix per category (requirement of the brief)")
    L.append("")
    L.append("| Category | Tokens | Share | Target band | Verdict |")
    L.append("|---|---:|---:|---:|---|")
    L.extend(mix_lines)
    L.append("")
    L.append(f"**Overall mix: {'COMPLIANT' if mix_ok else 'NON-COMPLIANT'}**")
    L.append("")

    L.append("## Documents per category")
    L.append("")
    L.append("| Category | Documents | Tokens | Mean |")
    L.append("|---|---:|---:|---:|")
    for cat in ("cat1", "cat2", "cat3"):
        n = by_cat.get(cat, 0)
        t = by_cat_tokens.get(cat, 0)
        L.append(f"| {cat} | {n} | {t:,} | {t // n if n else 0} |")
    L.append(f"| **total** | **{len(rows)}** | **{total_tokens:,}** | "
             f"**{total_tokens // len(rows) if rows else 0}** |")
    L.append("")

    L.append("## Per tier")
    for tier in sorted(by_tier):
        L.append(f"- {tier}: {by_tier[tier]:,} tokens")
    L.append("")

    L.append("## Per license")
    L.append("")
    L.append("| License | Documents |")
    L.append("|---|---:|")
    for lic in sorted(by_license, key=lambda x: -by_license[x]):
        flag = "  <- outside allowlist, inclusion on a recorded decision" \
            if lic == "no-license" or lic.startswith("flagged:") else ""
        L.append(f"| {lic}{flag} | {by_license[lic]} |")
    L.append("")

    L.append("## Per source nature")
    for st in sorted(by_source_type, key=lambda x: -by_source_type[x]):
        L.append(f"- {st}: {by_source_type[st]} documents")
    L.append("")

    if dropped:
        L.append("## Dropped at merge time")
        L.append("")
        L.append("| Reason | Count |")
        L.append("|---|---:|")
        for reason, n in dropped.most_common():
            L.append(f"| {reason} | {n} |")
        L.append("")

    L.append("## Regeneration")
    L.append("")
    L.append("```bash")
    L.append("./rebuild_dataset.sh          # everything, in order")
    L.append("```")
    L.append("")
    L.append("The per-category corpora remain the source of truth; this "
             "file is a regenerable derivative.")

    paths.full_stats_path().write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description="Merge the cat1/cat2/cat3 corpora into a single corpus")
    ap.add_argument("--shuffle", action="store_true",
                    help="deterministic shuffle (fixed seed) of the records")
    ap.add_argument("--no-cross-dedup", action="store_true",
                    help="disable deduplication between categories")
    ap.add_argument("--dedup-threshold", type=float, default=0.85)
    args = ap.parse_args()

    report = RunReport("merge-corpus", title="Full corpus — merge")
    checker = ContaminationChecker.from_config()
    index = DuplicateIndex(threshold=args.dedup_threshold)

    print(f"Project root  : {paths.PROJECT_ROOT}")
    print(f"Contamination : {checker.describe()}")
    print(f"Cross-dedup   : "
          f"{'disabled' if args.no_cross_dedup else index.describe()}\n")

    kept: List[dict] = []
    seen_ids: set = set()
    dropped: Counter = Counter()
    by_cat: Counter = Counter()
    by_cat_tokens: Counter = Counter()

    for category in ("cat1", "cat2", "cat3"):
        rows = load_category(category)
        if not rows:
            print(f"  [{category}] corpus missing — category skipped")
            report.warn(category, reason=f"corpus missing: "
                                         f"{paths.corpus_path(category)}")
            continue

        n_kept = 0
        for rec in rows:
            try:
                validate_record(rec)
            except ValueError as exc:
                dropped["invalid record"] += 1
                report.fail(rec.get("id", "?"), kind=category, reason=str(exc))
                continue

            if rec["id"] in seen_ids:
                # Two categories must never produce the same id: that would
                # be a naming collision, not a content duplicate.
                dropped["colliding identifier"] += 1
                report.fail(rec["id"], kind=category,
                            reason="identifier already present in another "
                                   "category — naming collision")
                continue

            verdict = checker.check(rec["text"])
            if verdict.is_contaminated:
                dropped["contamination"] += 1
                report.skip(rec["id"], kind=category,
                            reason=f"CONTAMINATION — {verdict.describe()}")
                continue

            if not args.no_cross_dedup:
                dup = index.check(rec["text"])
                if dup.is_duplicate:
                    dropped[f"cross-category duplicate ({dup.kind})"] += 1
                    report.skip(rec["id"], kind=category,
                                reason=f"{dup.describe()} — already present "
                                       f"in the merged corpus")
                    continue
                index.add(rec["id"], rec["text"])

            seen_ids.add(rec["id"])
            kept.append(rec)
            by_cat[category] += 1
            by_cat_tokens[category] += rec["n_tokens"]
            n_kept += 1

        print(f"  [{category}] {len(rows)} read -> {n_kept} kept "
              f"({by_cat_tokens[category]:,} tokens)")
        report.ok(category, detail=f"{n_kept}/{len(rows)} kept, "
                                   f"{by_cat_tokens[category]:,} tokens")

    if args.shuffle:
        # Fixed seed: two merges give the same order, otherwise the corpus
        # is no longer reproducible.
        random.Random(SHUFFLE_SEED).shuffle(kept)

    out = paths.full_corpus_path()
    paths.ensure_dirs(out.parent)
    with out.open("w", encoding="utf-8") as f:
        for rec in kept:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    mix_ok, mix_lines = check_mix(by_cat_tokens)
    total_tokens = sum(by_cat_tokens.values())
    contamination_summary = (
        f"PASSED — 0 overlap over {len(kept)} documents"
        if not dropped["contamination"]
        else f"{dropped['contamination']} document(s) excluded")
    n_cross = sum(v for k, v in dropped.items() if k.startswith("cross-category"))
    dedup_desc = ("disabled" if args.no_cross_dedup
                  else f"{n_cross} cross-category duplicate(s) removed "
                       f"({index.describe()})")

    report.info("Total tokens", f"{total_tokens:,}")
    report.info("Mix", "COMPLIANT" if mix_ok else "NON-COMPLIANT")
    report.info("Contamination", contamination_summary)
    report.info("Cross-category deduplication", dedup_desc)
    report.info("Ordering", "shuffled (fixed seed)" if args.shuffle
                else "by category")
    report_path = report.write()

    write_stats(kept, by_cat=by_cat, by_cat_tokens=by_cat_tokens,
                mix_ok=mix_ok, mix_lines=mix_lines, dropped=dropped,
                dedup_desc=dedup_desc,
                contamination_summary=contamination_summary,
                report_path=report_path)

    print(f"\nFull corpus : {out}")
    print(f"  {len(kept)} records, {total_tokens:,} tokens")
    for line in mix_lines:
        print("   ", line)
    print(f"  mix           : {'COMPLIANT' if mix_ok else 'NON-COMPLIANT'}")
    print(f"  contamination : {contamination_summary}")
    print(f"  cross-dedup   : {dedup_desc}")
    if dropped:
        print(f"  dropped : {dict(dropped)}")
    print(f"  stats   : {paths.full_stats_path()}")
    print(f"  report  : {report_path}")

    raise SystemExit(0 if mix_ok else 1)


if __name__ == "__main__":
    main()
