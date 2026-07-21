"""
Entry point of PHASE 2 (transformation) -- category 3.

Reads the phase-1 raw files (collected URDFs + manually placed PDF
manuals), applies the license barrier, and produces a unified JSONL corpus
(1 record per source) plus statistics.

Runnable from any directory:
    python3 /path/to/src/cat3/build_corpus.py
    python3 .../build_corpus.py --sources urdf,pdf
    python3 .../build_corpus.py --provider gemini
    python3 .../build_corpus.py --sources urdf,pdf --ocr

NO skip is silent: every robot set aside (missing manual, non-compliant
license, empty extraction, contamination) is logged and counted in the
final report.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> src/

import argparse
import json
from collections import Counter
from datetime import datetime, timezone

from common import paths
from common.contamination import ContaminationChecker
from common.license_utils import classify_license, is_collectible
from common.llm_provider import get_provider
from common.run_report import RunReport
from common.tokenizer_utils import TokenCounter
from common.corpus_assembler import assemble_record, validate_record
from cat3 import urdf_adapter, pdf_adapter

CATEGORY = "cat3"
METADATA_PATH = paths.metadata_path(CATEGORY)
MANUALS_DIR = paths.raw_kind_dir(CATEGORY, "manuals")
CORPUS_PATH = paths.corpus_path(CATEGORY)
STATS_PATH = paths.stats_path(CATEGORY)

# The manifest is CONFIGURATION: it lives with the code. The old location
# (inside the data tree) is still tolerated so nothing breaks, but flagged.
MANIFEST_PATH = paths.code_dir(CATEGORY) / "pdf_manifest.json"
LEGACY_MANIFEST_PATH = MANUALS_DIR / "pdf_manifest.json"

ALLOW_NO_LICENSE_FOR = {"agilex_ranger_mini_v3"}


def _resolve_manifest() -> Path | None:
    if MANIFEST_PATH.exists():
        return MANIFEST_PATH
    if LEGACY_MANIFEST_PATH.exists():
        print(f"  [note] manifest found at the old location "
              f"({LEGACY_MANIFEST_PATH}). Recommended location: {MANIFEST_PATH}")
        return LEGACY_MANIFEST_PATH
    return None


# --------------------------------------------------------------------------
# URDF path
# --------------------------------------------------------------------------

def _iter_urdf(provider, drafts: list, skipped: list, report: RunReport) -> None:
    if not METADATA_PATH.exists():
        print(f"  [urdf] no metadata file: {METADATA_PATH}")
        print("         -> run collect_pilot.py first")
        report.fail("(urdf path)", kind="urdf",
                    reason=f"metadata missing: {METADATA_PATH} — "
                           f"run collect_pilot.py first")
        return

    for line in METADATA_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        meta = json.loads(line)
        rid = meta["robot_id"]
        status = meta["license_status"]

        if not is_collectible(status, allow_no_license_override=rid in ALLOW_NO_LICENSE_FOR):
            reason = f"non-compliant license ({status})"
            skipped.append((rid, "urdf", reason))
            report.skip(rid, kind="urdf", reason=reason)
            continue

        urdf_path = paths.from_relative(meta["raw_urdf_path"])
        if not urdf_path.exists():
            reason = f"file missing: {urdf_path}"
            skipped.append((rid, "urdf", reason))
            report.skip(rid, kind="urdf", reason=reason)
            continue

        try:
            draft = urdf_adapter.adapt(
                rid, urdf_path,
                license_status=status,
                url=meta.get("repo_url", ""),
                source_name=meta.get("source_type", "robot_descriptions"),
                provider=provider,
            )
        except Exception as exc:  # a broken URDF does not stop the run
            skipped.append((rid, "urdf", f"FAILED: {exc}"))
            report.fail(rid, kind="urdf", exc=exc)
            continue

        for note in draft.provenance.get("parse_notes", []):
            report.warn(rid, kind="urdf", reason=note)
        drafts.append(draft)


# --------------------------------------------------------------------------
# PDF path
# --------------------------------------------------------------------------

def _iter_pdf(provider, drafts: list, skipped: list, report: RunReport, *,
              allow_proprietary: bool, llm_format: bool,
              use_ocr: bool, ocr_max_pages) -> None:
    manifest_path = _resolve_manifest()
    if manifest_path is None:
        print(f"  [pdf] manifest not found. Expected: {MANIFEST_PATH}")
        report.fail("(pdf path)", kind="pdf_manual",
                    reason=f"manifest not found, expected: {MANIFEST_PATH}")
        return

    manuals = json.loads(manifest_path.read_text(encoding="utf-8"))["manuals"]
    print(f"  [pdf] manifest: {manifest_path} ({len(manuals)} entries)")
    print(f"  [pdf] manual directory: {MANUALS_DIR}")
    report.info("PDF manifest", f"`{paths.to_relative(manifest_path)}` "
                                f"({len(manuals)} entries)")

    for m in manuals:
        rid = m["robot_id"]
        robot_dir = MANUALS_DIR / rid
        pdf_path = pdf_adapter.find_pdf(robot_dir, m.get("target_filename"))

        if pdf_path is None:
            reason = f"no .pdf in {paths.to_relative(robot_dir)}"
            skipped.append((rid, "pdf_manual", reason))
            report.skip(rid, kind="pdf_manual", reason=reason)
            continue

        status = classify_license(m.get("license_spdx"))
        # Per-robot decision in the manifest, or a global one via the CLI.
        per_entry = bool(m.get("allow_no_license", False))
        override = per_entry or allow_proprietary
        if not is_collectible(status, allow_no_license_override=override):
            reason = (f"non-compliant license ({status}) -- use "
                      f"--allow-proprietary-pdf or allow_no_license in the manifest")
            skipped.append((rid, "pdf_manual", reason))
            report.skip(rid, kind="pdf_manual", reason=reason)
            continue

        def _progress(page, total, conf, info=None, _rid=rid):
            extra = ""
            if info:
                if info.get("bands"):
                    extra = f" band {info['band']}/{info['bands']}"
                extra += f" @{info.get('dpi')}dpi"
            print(f"  [pdf] {_rid} OCR page {page}/{total}{extra} "
                  f"(confidence {conf:.2f})", flush=True)

        try:
            draft = pdf_adapter.adapt(
                rid, pdf_path,
                license_status=status,
                url=m.get("url", ""),
                source_name=f"manual:{rid}",
                provider=provider,
                use_llm_format=llm_format,
                use_ocr=use_ocr,
                ocr_max_pages=ocr_max_pages,
                ocr_progress=_progress,
            )
        except Exception as exc:  # corrupt / scanned PDF -> logged, continue
            skipped.append((rid, "pdf_manual", f"FAILED: {exc}"))
            report.fail(rid, kind="pdf_manual", exc=exc)
            continue

        drafts.append(draft)
        print(f"  [pdf] {rid} <- {pdf_path.name}"
              f"{' [OCR]' if draft.ocr else ''}")
        if status == "no-license":
            origin = ("manifest (allow_no_license)" if per_entry
                      else "--allow-proprietary-pdf option")
            report.warn(rid, kind="pdf_manual",
                        reason=f"manual without a compliant license included "
                               f"on an explicit decision — {origin}; "
                               f"{m.get('license_note', '')}")
        if draft.ocr:
            report.warn(rid, kind="pdf_manual",
                        reason=f"text obtained through OCR "
                               f"({draft.provenance.get('ocr_backend')}, "
                               f"mean confidence "
                               f"{draft.provenance.get('ocr_mean_confidence')}) "
                               f"— digit reliability lower than a native "
                               f"extraction")


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------

def write_stats(rows: list, skipped: list, tc: TokenCounter, *,
                contamination_summary: str, report_path=None) -> None:
    by_type = Counter(r["source_type"] for r in rows)
    tokens_by_type: Counter = Counter()
    for r in rows:
        tokens_by_type[r["source_type"]] += r["n_tokens"]
    total_tokens = sum(r["n_tokens"] for r in rows)
    by_license = Counter(r["license"] for r in rows)
    ocr_rows = [r for r in rows if r.get("ocr")]

    lines = ["# Category 3 corpus — statistics", ""]
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Project root: `{paths.PROJECT_ROOT}`")
    lines.append(f"- Records: {len(rows)}")
    lines.append(f"- Total tokens: {total_tokens} "
                 f"({'Qwen3 exact' if tc.is_exact else 'APPROXIMATE — ' + tc.describe()})")
    lines.append(f"- Contamination check: {contamination_summary}")
    if report_path is not None:
        lines.append(f"- Run report: `{paths.to_relative(report_path)}`")
    lines.append("")

    lines.append("## Per source type")
    for t in sorted(by_type):
        n = by_type[t]
        avg = tokens_by_type[t] // n if n else 0
        lines.append(f"- {t}: {n} records, {tokens_by_type[t]} tokens "
                     f"(mean {avg})")

    lines.append("")
    lines.append("## Per license")
    for lic in sorted(by_license):
        marker = "  <- outside allowlist, inclusion on an explicit decision" \
            if lic == "no-license" or lic.startswith("flagged:") else ""
        lines.append(f"- {lic}: {by_license[lic]}{marker}")

    lines.append("")
    lines.append("## Extraction quality")
    lines.append(f"- Native extraction: {len(rows) - len(ocr_rows)}")
    lines.append(f"- Text from OCR: {len(ocr_rows)}"
                 + (" (`ocr: true` field, filterable)" if ocr_rows else ""))
    for r in ocr_rows:
        lines.append(f"  - `{r['id']}` — mean confidence "
                     f"{r.get('ocr_confidence')}")

    if skipped:
        lines.append("")
        lines.append(f"## Skipped ({len(skipped)})")
        for rid, kind, reason in skipped:
            lines.append(f"- `{rid}` ({kind}): {reason}")
    STATS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 2 -- build the cat3 corpus")
    ap.add_argument("--provider", default=None, help="anthropic|openai|gemini|template")
    ap.add_argument("--sources", default="urdf,pdf",
                    help="urdf,pdf (comma-separated)")
    ap.add_argument("--allow-proprietary-pdf", action="store_true",
                    help="include manuals without a compliant license "
                         "(explicit decision)")
    ap.add_argument("--llm-format-pdf", action="store_true",
                    help="run manuals through the LLM for formatting (extractive)")
    ap.add_argument("--ocr", action="store_true",
                    help="run OCR on scanned PDFs (no text layer). The "
                         "produced text is marked ocr:true in the corpus.")
    ap.add_argument("--ocr-max-pages", type=int, default=None,
                    help="cap the number of OCR'd pages per document")
    args = ap.parse_args()

    report = RunReport("cat3-build-corpus", category=CATEGORY,
                       title="Category 3 — phase 2 (corpus build)")

    provider = get_provider(args.provider)
    tc = TokenCounter()
    sources = {s.strip() for s in args.sources.split(",") if s.strip()}
    checker = ContaminationChecker.from_config()

    print(f"Project root  : {paths.PROJECT_ROOT}")
    print(f"LLM provider  : {provider.name} | tokenizer: {tc.describe()}")
    print(f"Sources       : {', '.join(sorted(sources))}")
    print(f"Contamination : {checker.describe()}")
    print(f"OCR           : {'enabled' if args.ocr else 'disabled'}\n")

    report.info("Sources", ", ".join(sorted(sources)))
    report.info("LLM provider", provider.name)
    report.info("Tokenizer", tc.describe())
    report.info("Contamination", checker.describe())
    report.info("OCR", "enabled" if args.ocr else "disabled")
    report.info("--allow-proprietary-pdf", args.allow_proprietary_pdf)

    drafts: list = []
    skipped: list = []
    if "urdf" in sources:
        _iter_urdf(provider, drafts, skipped, report)
    if "pdf" in sources:
        _iter_pdf(provider, drafts, skipped, report,
                  allow_proprietary=args.allow_proprietary_pdf,
                  llm_format=args.llm_format_pdf,
                  use_ocr=args.ocr,
                  ocr_max_pages=args.ocr_max_pages)

    paths.ensure_dirs(CORPUS_PATH.parent)
    rows = []
    n_contaminated = 0
    with CORPUS_PATH.open("w", encoding="utf-8") as f:
        for draft in drafts:
            # Contamination check: a document overlapping the evaluation
            # scenario does not enter the corpus, however good it is
            # otherwise.
            verdict = checker.check(draft.text)
            if verdict.is_contaminated:
                n_contaminated += 1
                reason = f"CONTAMINATION — {verdict.describe()}"
                skipped.append((draft.robot_id, draft.source_type, reason))
                report.skip(draft.robot_id, kind=draft.source_type, reason=reason)
                continue

            rec = assemble_record(draft, category=CATEGORY, token_counter=tc)
            validate_record(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows.append(rec)
            report.ok(draft.robot_id, kind=draft.source_type,
                      detail=f"{rec['n_tokens']} tokens, license {rec['license']}"
                             + (" [OCR]" if rec.get("ocr") else ""))

    contamination_summary = (
        f"PASSED — 0 overlap over {len(drafts)} documents examined "
        f"({checker.describe()})" if n_contaminated == 0 else
        f"{n_contaminated} document(s) excluded out of {len(drafts)} examined"
    )
    report.info("Contamination result", contamination_summary)

    report_path = report.write()
    write_stats(rows, skipped, tc,
                contamination_summary=contamination_summary,
                report_path=report_path)

    by_type = Counter(r["source_type"] for r in rows)
    print(f"\nCorpus written: {CORPUS_PATH}")
    print(f"  {len(rows)} records " +
          " | ".join(f"{t}: {n}" for t, n in sorted(by_type.items())))
    print(f"  contamination: {contamination_summary}")
    if skipped:
        print(f"  {len(skipped)} skipped (details in {STATS_PATH}):")
        for rid, kind, reason in skipped[:10]:
            print(f"    - {rid} ({kind}): {reason}")
        if len(skipped) > 10:
            print(f"    ... and {len(skipped) - 10} more")
    print(f"  report: {report_path}")


if __name__ == "__main__":
    main()
