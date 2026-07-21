"""
Entry point for PHASE 1 (collection) -- category 2 (HMRS Data).

Two paths, one output:

  repositories  shallow clone + license cross-check + glob selection,
                exactly as cat1 (common/git_repo.py).
  papers        one-time download of the arXiv full text (HTML or PDF) into
                data/cat2/raw/papers/<arxiv_id>/paper.txt.

As with the other categories, nothing is transformed here: phase 2 must be
able to replay the quotas without re-downloading 43 papers.

Runnable from any directory:
    python3 /path/to/src/cat2/collect_hmrs.py
    python3 .../collect_hmrs.py --only repos     # or: papers
    python3 .../collect_hmrs.py --refresh
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> src/

import argparse
import json
import shutil
import time
from datetime import datetime, timezone

from common import paths
from common.git_repo import clone, select_files
from common.license_utils import classify_license, is_collectible
from common.run_report import RunReport
from cat2 import fetch_arxiv
from cat2.sources import (PAPER_CATALOG, PAPER_LICENSE_SPDX, PAPER_TOKEN_BUDGET,
                          REPO_CATALOG, KIND_PAPER, RepoSource, total_budget)

CATEGORY = "cat2"
METADATA_PATH = paths.metadata_path(CATEGORY)
GIT_CACHE_DIR = paths.git_cache_dir(CATEGORY)
PAPERS_DIR = paths.raw_kind_dir(CATEGORY, "papers")

# No cat2 source is collected without a license.
ALLOW_NO_LICENSE_FOR: set = set()

# arXiv asks that automated requests be spaced out.
ARXIV_DELAY_S = 3.0


def _write_metadata_row(row: dict) -> None:
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with METADATA_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _drop_metadata_rows(source_ids: set) -> int:
    """
    Remove from the metadata the rows of the sources about to be
    re-collected.

    Without this, a partial collection (`--only`) APPENDS a second row for
    the same source: phase 2 then adapts the same files twice, and the
    deduplicator discards the entire second pass. Observed symptom:
    "141 candidates -> 0 unique".
    """
    if not METADATA_PATH.exists():
        return 0
    kept, dropped = [], 0
    for line in METADATA_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        if json.loads(line)["source_id"] in source_ids:
            dropped += 1
            continue
        kept.append(line)
    METADATA_PATH.write_text("\n".join(kept) + ("\n" if kept else ""),
                             encoding="utf-8")
    return dropped


# --------------------------------------------------------------------------
# Repository path
# --------------------------------------------------------------------------

def _collect_repo(source: RepoSource, report: RunReport, *, refresh: bool) -> None:
    print(f"[{source.source_id}] cloning ({source.repo_url} @ {source.repo_ref})...")
    checkout = clone(source.source_id, source.repo_url, source.repo_ref,
                     GIT_CACHE_DIR, refresh=refresh,
                     sparse_paths=source.sparse_paths)

    for w in checkout.warnings:
        report.warn(source.source_id, kind=source.kind,
                    reason=f"license: {w} (declared in the catalogue: "
                           f"{source.license_spdx})")
    if checkout.detected_license and checkout.detected_license != source.license_spdx:
        report.warn(source.source_id, kind=source.kind,
                    reason=f"LICENSE MISMATCH: catalogue="
                           f"{source.license_spdx}, detected="
                           f"{checkout.detected_license}. The catalogue wins; "
                           f"resolve by hand.")

    license_status = classify_license(source.license_spdx)
    if not is_collectible(license_status,
                          allow_no_license_override=source.source_id in ALLOW_NO_LICENSE_FOR):
        print(f"[{source.source_id}] SET ASIDE -- non-compliant license ({license_status})")
        report.skip(source.source_id, kind=source.kind,
                    reason=f"non-compliant license ({license_status})")
        return

    files = select_files(checkout.path, source.include_globs, source.exclude_globs)
    if not files:
        report.fail(source.source_id, kind=source.kind,
                    reason=f"no file matches the globs "
                           f"{source.include_globs} (branch {source.repo_ref}) "
                           f"— fix the catalogue")
        print(f"[{source.source_id}] NO FILE SELECTED")
        return

    dest_root = paths.item_dir(CATEGORY, source.kind, source.source_id)
    if dest_root.exists():
        shutil.rmtree(dest_root)
    n_bytes = 0
    for src in files:
        dst = dest_root / src.relative_to(checkout.path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        n_bytes += src.stat().st_size

    _write_metadata_row({
        "source_id": source.source_id,
        "display_name": source.display_name,
        "family": source.family,
        "kind": source.kind,
        "repo_url": source.repo_url,
        "repo_ref": source.repo_ref,
        "repo_commit": checkout.commit,
        "license_status": license_status,
        "license_declared": source.license_spdx,
        "license_detected": checkout.detected_license,
        "raw_dir": paths.to_relative(dest_root),
        "n_files": len(files),
        "n_bytes": n_bytes,
        "token_budget": source.token_budget,
        "url": source.url,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "notes": source.notes,
    })
    print(f"[{source.source_id}] collected -- {len(files)} files, "
          f"{n_bytes/1e6:.2f} MB, license {license_status}")
    report.ok(source.source_id, kind=source.kind,
              detail=f"{len(files)} files, {n_bytes/1e6:.2f} MB, "
                     f"license {license_status}, commit {checkout.commit[:8]}")


# --------------------------------------------------------------------------
# Paper path
# --------------------------------------------------------------------------

def _collect_papers(report: RunReport, *, refresh: bool) -> None:
    license_status = classify_license(PAPER_LICENSE_SPDX)
    if not is_collectible(license_status):
        report.skip("(papers)", kind=KIND_PAPER,
                    reason=f"license {license_status} not compliant")
        return

    tmp_dir = GIT_CACHE_DIR.parent / "arxiv_tmp"
    n_ok = 0
    for i, paper in enumerate(PAPER_CATALOG, start=1):
        dest_dir = PAPERS_DIR / paper.arxiv_id
        dest = dest_dir / "paper.txt"

        if dest.exists() and not refresh:
            text = dest.read_text(encoding="utf-8")
            print(f"  [{paper.arxiv_id}] already present ({len(text)} chars)")
        else:
            try:
                result = fetch_arxiv.fetch(paper.arxiv_id, paper.fetch, tmp_dir)
            except Exception as exc:  # noqa: BLE001 -- one paper blocks nothing
                print(f"  [{paper.arxiv_id}] FAILED: {exc}")
                report.fail(paper.arxiv_id, kind=KIND_PAPER, exc=exc)
                time.sleep(ARXIV_DELAY_S)
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest.write_text(result.text, encoding="utf-8")
            text = result.text
            print(f"  [{paper.arxiv_id}] {paper.fetch} -- {len(text)} chars "
                  f"({i}/{len(PAPER_CATALOG)})")
            time.sleep(ARXIV_DELAY_S)

        _write_metadata_row({
            "source_id": f"arxiv-{paper.arxiv_id}",
            "display_name": paper.title,
            "family": "papers",
            "kind": KIND_PAPER,
            "repo_url": paper.url,
            "repo_ref": paper.fetch,
            "repo_commit": paper.arxiv_id,
            "license_status": license_status,
            "license_declared": PAPER_LICENSE_SPDX,
            "license_detected": PAPER_LICENSE_SPDX,   # read via arXiv OAI-PMH
            "raw_dir": paths.to_relative(dest_dir),
            "n_files": 1,
            "n_bytes": len(text.encode("utf-8")),
            # The budget is carried by the whole family, not per paper: the
            # papers share a single cap in phase 2.
            "token_budget": PAPER_TOKEN_BUDGET,
            "url": paper.url,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "notes": f"arXiv {paper.arxiv_id}, CC-BY-4.0 license verified "
                     f"through OAI-PMH, full text via the {paper.fetch} path",
        })
        n_ok += 1
        report.ok(paper.arxiv_id, kind=KIND_PAPER,
                  detail=f"{len(text)} characters, {paper.fetch} path")

    shutil.rmtree(tmp_dir, ignore_errors=True)
    print(f"\n  papers collected: {n_ok}/{len(PAPER_CATALOG)}")


# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 1 -- cat2 collection")
    ap.add_argument("--only", default=None, choices=["repos", "papers"],
                    help="process only one of the two paths")
    ap.add_argument("--refresh", action="store_true",
                    help="re-clone / re-download instead of using the cache")
    args = ap.parse_args()

    report = RunReport("cat2-collect", category=CATEGORY,
                       title="Category 2 — phase 1 (HMRS collection)")
    print(f"Project root : {paths.PROJECT_ROOT}")
    print(f"Repositories : {len(REPO_CATALOG)}")
    print(f"Papers       : {len(PAPER_CATALOG)} (all CC-BY-4.0)")
    print(f"Total budget : {total_budget():,} tokens (phase-2 caps)\n")
    report.info("Repositories", len(REPO_CATALOG))
    report.info("arXiv papers", f"{len(PAPER_CATALOG)} (all CC-BY-4.0)")
    report.info("Total declared budget", f"{total_budget():,} tokens")

    paths.ensure_dirs(METADATA_PATH.parent, GIT_CACHE_DIR, PAPERS_DIR)
    if args.only is None:
        if METADATA_PATH.exists():
            METADATA_PATH.unlink()
    else:
        affected = ({s.source_id for s in REPO_CATALOG} if args.only == "repos"
                    else {f"arxiv-{p.arxiv_id}" for p in PAPER_CATALOG})
        n = _drop_metadata_rows(affected)
        if n:
            print(f"[metadata] {n} row(s) replaced for the '{args.only}' "
                  f"path\n")

    if args.only in (None, "repos"):
        for source in REPO_CATALOG:
            try:
                _collect_repo(source, report, refresh=args.refresh)
            except Exception as exc:  # noqa: BLE001
                print(f"[{source.source_id}] FAILED: {exc}")
                report.fail(source.source_id, kind=source.kind, exc=exc)

    if args.only in (None, "papers"):
        print("\n--- arXiv papers ---")
        _collect_papers(report, refresh=args.refresh)

    report_path = report.write()
    c = report.counts()
    print(f"\nDone: {c['ok']} collected, {c['skip']} set aside, "
          f"{c['fail']} failed.")
    print(f"Metadata : {METADATA_PATH}")
    print(f"Report   : {report_path}")


if __name__ == "__main__":
    main()
