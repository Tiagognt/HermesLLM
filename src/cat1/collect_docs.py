"""
Entry point for PHASE 1 (collection) -- category 1 (General Robot Data).

For each source in the catalogue (`sources.py`):
  1. shallow clone of the repository on a given reference (sparse if needed)
  2. read the LICENSE file and CROSS-CHECK the declared SPDX id
  3. license barrier (license_utils)
  4. select files by glob and copy them to
     data/cat1/raw/<kind>/<source_id>/<relative_path>
  5. append one line to data/cat1/metadata/collection_metadata.jsonl

As in cat3, this script transforms nothing: `build_corpus.py` (phase 2)
produces the corpus. It must be possible to regenerate the corpus -- and in
particular to replay the token quotas -- without re-cloning 28
repositories.

Runnable from any directory:
    python3 /path/to/src/cat1/collect_docs.py
    python3 .../collect_docs.py --only ros2_documentation,nav2_docs
    python3 .../collect_docs.py --refresh        # re-clone instead of cache
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> src/

import argparse
import json
import shutil
from datetime import datetime, timezone

from common import paths
from common.git_repo import clone, select_files
from common.license_utils import classify_license, is_collectible
from common.run_report import RunReport
from cat1.sources import CATALOG, RepoSource, total_budget

CATEGORY = "cat1"
METADATA_PATH = paths.metadata_path(CATEGORY)
GIT_CACHE_DIR = paths.git_cache_dir(CATEGORY)

# No cat1 source is collected without a license: unlike cat3 (vendor
# manuals dropped in by hand), everything here is public content whose
# license is verifiable. The set stays empty on purpose.
ALLOW_NO_LICENSE_FOR: set = set()


def _write_metadata_row(row: dict) -> None:
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with METADATA_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _drop_metadata_rows(source_ids: set) -> int:
    """
    Remove from the metadata the rows of the sources about to be
    re-collected. Without this, `--only` APPENDS a second row for the same
    source, phase 2 adapts the same files twice, and the deduplicator
    discards the whole second pass.
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


def _copy_selection(files, repo_root: Path, dest_root: Path) -> int:
    """Copy while preserving the relative tree (used later for diversity)."""
    if dest_root.exists():
        shutil.rmtree(dest_root)
    n = 0
    for src in files:
        rel = src.relative_to(repo_root)
        dst = dest_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        n += 1
    return n


def _collect_one(source: RepoSource, report: RunReport, *, refresh: bool) -> None:
    print(f"[{source.source_id}] cloning ({source.repo_url} @ {source.repo_ref})...")
    checkout = clone(source.source_id, source.repo_url, source.repo_ref,
                     GIT_CACHE_DIR, refresh=refresh,
                     sparse_paths=source.sparse_paths)

    # -- license cross-check -----------------------------------------------
    # The catalogue is authoritative (human verification), but any
    # disagreement with the real LICENSE file must surface: that is exactly
    # the kind of discrepancy which, unreported, ends up polluting the
    # corpus.
    for w in checkout.warnings:
        report.warn(source.source_id, kind=source.kind,
                    reason=f"license: {w} (declared in the catalogue: "
                           f"{source.license_spdx})")
    if (checkout.detected_license
            and checkout.detected_license != source.license_spdx):
        report.warn(
            source.source_id, kind=source.kind,
            reason=f"LICENSE MISMATCH: catalogue={source.license_spdx}, "
                   f"detected in {checkout.license_file.name if checkout.license_file else '?'}"
                   f"={checkout.detected_license}. The catalogue wins; "
                   f"resolve by hand.")

    license_status = classify_license(source.license_spdx)
    if not is_collectible(license_status,
                          allow_no_license_override=source.source_id in ALLOW_NO_LICENSE_FOR):
        print(f"[{source.source_id}] SET ASIDE -- non-compliant license ({license_status})")
        report.skip(source.source_id, kind=source.kind,
                    reason=f"non-compliant license ({license_status})")
        return

    # -- selection and copy -------------------------------------------------
    files = select_files(checkout.path, source.include_globs, source.exclude_globs)
    if not files:
        # A glob matching nothing is almost always a catalogue error
        # (branch or tree layout changed): never silent.
        report.fail(source.source_id, kind=source.kind,
                    reason=f"no file matches the globs "
                           f"{source.include_globs} in {checkout.path.name} "
                           f"(branch {source.repo_ref}) — fix the catalogue")
        print(f"[{source.source_id}] NO FILE SELECTED")
        return

    dest_root = paths.item_dir(CATEGORY, source.kind, source.source_id)
    n_files = _copy_selection(files, checkout.path, dest_root)
    n_bytes = sum(f.stat().st_size for f in files)

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
        "license_file": (paths.to_relative(checkout.license_file)
                         if checkout.license_file else None),
        "raw_dir": paths.to_relative(dest_root),
        "n_files": n_files,
        "n_bytes": n_bytes,
        "token_budget": source.token_budget,
        "url": source.url,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "notes": source.notes,
    })
    print(f"[{source.source_id}] collected -- {n_files} files, "
          f"{n_bytes/1e6:.2f} MB, license {license_status}")
    report.ok(source.source_id, kind=source.kind,
              detail=f"{n_files} files, {n_bytes/1e6:.2f} MB, "
                     f"license {license_status}, commit {checkout.commit[:8]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 1 -- cat1 collection")
    ap.add_argument("--only", default=None,
                    help="restrict to these source_ids (comma-separated)")
    ap.add_argument("--refresh", action="store_true",
                    help="re-clone repositories instead of reusing the cache")
    args = ap.parse_args()

    selection = CATALOG
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        selection = [s for s in CATALOG if s.source_id in wanted]
        unknown = wanted - {s.source_id for s in CATALOG}
        if unknown:
            raise SystemExit(f"unknown source_id(s): {sorted(unknown)}")

    report = RunReport("cat1-collect", category=CATEGORY,
                       title="Category 1 — phase 1 (source collection)")
    print(f"Project root : {paths.PROJECT_ROOT}")
    print(f"Git cache    : {GIT_CACHE_DIR}")
    print(f"Sources      : {len(selection)} / {len(CATALOG)}")
    print(f"Total budget : {total_budget():,} tokens (phase-2 caps)\n")
    report.info("Sources processed", f"{len(selection)} / {len(CATALOG)}")
    report.info("Total declared budget", f"{total_budget():,} tokens")
    report.info("Git cache", f"`{paths.to_relative(GIT_CACHE_DIR)}`")

    paths.ensure_dirs(METADATA_PATH.parent, GIT_CACHE_DIR)
    if not args.only:
        if METADATA_PATH.exists():
            METADATA_PATH.unlink()
    else:
        n = _drop_metadata_rows({s.source_id for s in selection})
        if n:
            print(f"[metadata] {n} row(s) replaced\n")

    for source in selection:
        try:
            _collect_one(source, report, refresh=args.refresh)
        except Exception as exc:  # noqa: BLE001 -- a broken source stops nothing
            print(f"[{source.source_id}] FAILED: {exc}")
            report.fail(source.source_id, kind=source.kind, exc=exc)

    report_path = report.write()
    c = report.counts()
    print(f"\nDone: {c['ok']} collected, {c['skip']} set aside, "
          f"{c['fail']} failed out of {len(selection)}.")
    print(f"Metadata : {METADATA_PATH}")
    print(f"Report   : {report_path}")


if __name__ == "__main__":
    main()
