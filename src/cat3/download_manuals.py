"""
Helper for MANUALLY downloading the PDF manuals.

This script does not download anything on your behalf (vendor sites usually
require a browser or a login). It:
  1. creates the data/cat3/raw/manuals/<robot_id>/ tree,
  2. prints a checklist (robot, document, URL, license),
  3. shows which ones are already present AND under what filename.

ANY .pdf filename is accepted inside a robot's directory (g1_manual.pdf,
technical_manual.pdf...): no renaming needed.

Runnable from any directory:
    python3 /path/to/src/cat3/download_manuals.py
    python3 .../download_manuals.py --check     # check only, create nothing
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> src/

import argparse
import json

from common import paths
from common.license_utils import classify_license
from cat3.pdf_adapter import find_pdf

CATEGORY = "cat3"
MANUALS_DIR = paths.raw_kind_dir(CATEGORY, "manuals")
MANIFEST_PATH = paths.code_dir(CATEGORY) / "pdf_manifest.json"
LEGACY_MANIFEST_PATH = MANUALS_DIR / "pdf_manifest.json"


def load_manifest() -> list:
    path = MANIFEST_PATH if MANIFEST_PATH.exists() else LEGACY_MANIFEST_PATH
    if not path.exists():
        raise SystemExit(f"Manifest not found. Expected: {MANIFEST_PATH}")
    if path is LEGACY_MANIFEST_PATH:
        print(f"[note] manifest at the old location ({path}).")
        print(f"       Recommended location: {MANIFEST_PATH}\n")
    return json.loads(path.read_text(encoding="utf-8"))["manuals"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="check presence only")
    args = ap.parse_args()

    manuals = load_manifest()
    print(f"Project root  : {paths.PROJECT_ROOT}")
    print(f"Target folder : {MANUALS_DIR}\n")

    present = collectible_now = 0
    for m in manuals:
        rid = m["robot_id"]
        robot_dir = MANUALS_DIR / rid
        if not args.check:
            robot_dir.mkdir(parents=True, exist_ok=True)

        found = find_pdf(robot_dir, m.get("target_filename"))
        status = classify_license(m.get("license_spdx"))
        allowed = bool(m.get("allow_no_license", False))
        present += found is not None
        if found is not None and (status not in ("no-license",) or allowed):
            collectible_now += 1

        mark = f"YES ({found.name})" if found else "—"
        print(f"{rid:24s} {mark}")
        print(f"{'':24s}   {m['document']}")
        print(f"{'':24s}   URL      : {m['url']}")
        print(f"{'':24s}   folder   : {robot_dir}")
        print(f"{'':24s}   license  : {status}"
              f"{'  [override allowed in the manifest]' if allowed else ''}")

    print("-" * 90)
    print(f"{present}/{len(manuals)} manuals present on disk.")
    print(f"{collectible_now}/{len(manuals)} would pass the license barrier as-is.")
    print("\nTo include proprietary manuals, either:")
    print("  - build_corpus.py --sources pdf --allow-proprietary-pdf   (global decision)")
    print("  - \"allow_no_license\": true on the manifest entry          (per-robot decision)")


if __name__ == "__main__":
    main()
