"""
Entry point of the collection pilot (category 3 -- URDF & Robot Specs).

For each robot in the catalogue (sources.py):
  1. fetch the source file (via robot_descriptions.py or direct git)
  2. if it is a Xacro, render it to URDF (xacro_render.py)
  3. classify the license per the project rules (license_utils.py)
  4. copy the raw file(s) to data/cat3/raw/urdf/<robot_id>/
  5. append a line to data/cat3/metadata/collection_metadata.jsonl

This script does NOT transform anything into the final corpus: that is
build_corpus.py (phase 2), deliberately kept separate. This module only
produces raw files plus provenance/license metadata.

Runnable from any directory:
    python3 /path/to/src/cat3/collect_pilot.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> src/

import json
import shutil
from datetime import datetime, timezone

from common import paths
from common.license_utils import classify_license, is_collectible
from common.run_report import RunReport
from cat3.fetch_git_source import fetch_from_git
from cat3.fetch_robot_descriptions import fetch_via_robot_descriptions
from cat3.sources import PILOT_CATALOG, RobotSource, SourceType
from cat3.xacro_render import render_xacro_to_urdf

CATEGORY = "cat3"
RAW_URDF_DIR = paths.raw_kind_dir(CATEGORY, "urdf")
METADATA_PATH = paths.metadata_path(CATEGORY)
GIT_CACHE_DIR = paths.git_cache_dir(CATEGORY)

# Robots for which a missing license is explicitly accepted (project
# decision of 2026-07-15, to be revisited -- see sources.py).
ALLOW_NO_LICENSE_FOR = {"agilex_ranger_mini_v3"}


def _write_metadata_row(row: dict) -> None:
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with METADATA_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _collect_from_robot_descriptions(source: RobotSource, robot_dir: Path):
    result = fetch_via_robot_descriptions(source.description_module)

    raw_urdf_dest = robot_dir / "source.urdf"
    shutil.copy(result.urdf_path, raw_urdf_dest)

    raw_xacro_dest = None
    if result.xacro_path is not None:
        raw_xacro_dest = robot_dir / "source.xacro"
        shutil.copy(result.xacro_path, raw_xacro_dest)

    return {
        "license_status": classify_license(result.license_spdx),
        "repo_url": result.repo_url,
        "repo_ref": result.repo_commit,
        "source_file": str(result.xacro_path or result.urdf_path),
        "raw_urdf_dest": raw_urdf_dest,
        "raw_xacro_dest": raw_xacro_dest,
    }


def _collect_from_git(source: RobotSource, robot_dir: Path):
    GIT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fetched = fetch_from_git(
        repo_url=source.repo_url,
        ref=source.repo_ref,
        file_path_in_repo=source.file_path_in_repo,
        cache_root=GIT_CACHE_DIR,
    )

    raw_xacro_dest = robot_dir / "source.xacro"
    shutil.copy(fetched.file_path, raw_xacro_dest)

    urdf_text = render_xacro_to_urdf(fetched.file_path, fetched.repo_root)
    raw_urdf_dest = robot_dir / "source.urdf"
    raw_urdf_dest.write_text(urdf_text, encoding="utf-8")

    return {
        "license_status": classify_license(source.known_license_spdx),
        "repo_url": source.repo_url,
        "repo_ref": source.repo_ref,
        "source_file": str(fetched.file_path),
        "raw_urdf_dest": raw_urdf_dest,
        "raw_xacro_dest": raw_xacro_dest,
    }


def _robot_dir(source: RobotSource) -> Path:
    return RAW_URDF_DIR / source.robot_id


def _cleanup_if_empty(robot_dir: Path) -> bool:
    """
    Remove a robot's directory if it was left empty.

    The directory is created before fetching; when the fetch failed it used
    to stay on disk, empty, giving the illusion of a collected robot (real
    case: `tiago`, empty directory and absent from the metadata).
    """
    if robot_dir.is_dir() and not any(robot_dir.iterdir()):
        robot_dir.rmdir()
        return True
    return False


def _collect_one(source: RobotSource, report: RunReport) -> None:
    print(f"[{source.robot_id}] collecting...")
    robot_dir = _robot_dir(source)
    robot_dir.mkdir(parents=True, exist_ok=True)

    if source.source_type is SourceType.ROBOT_DESCRIPTIONS:
        outcome = _collect_from_robot_descriptions(source, robot_dir)
    elif source.source_type is SourceType.GIT_REPO:
        outcome = _collect_from_git(source, robot_dir)
    else:
        raise NotImplementedError(source.source_type)

    license_status = outcome["license_status"]
    allow_override = source.robot_id in ALLOW_NO_LICENSE_FOR
    collectible = is_collectible(license_status, allow_no_license_override=allow_override)

    if not collectible:
        print(f"[{source.robot_id}] SET ASIDE -- non-compliant license ({license_status})")
        shutil.rmtree(robot_dir, ignore_errors=True)
        report.skip(source.robot_id, kind=source.robot_class or "urdf",
                    reason=f"non-compliant license ({license_status}) — "
                           f"raw files removed from disk"
                           + (f". {source.notes}" if source.notes else ""))
        return

    _write_metadata_row({
        "robot_id": source.robot_id,
        "display_name": source.display_name,
        "robot_class": source.robot_class,
        "fleet_priority": source.fleet_priority,
        "source_type": source.source_type.value,
        "repo_url": outcome["repo_url"],
        "repo_ref": outcome["repo_ref"],
        "source_file": outcome["source_file"],
        "license_status": license_status,
        # Paths RELATIVE to the project root: the metadata stays valid if
        # the project is moved or cloned onto another machine.
        "raw_urdf_path": paths.to_relative(outcome["raw_urdf_dest"]),
        "raw_xacro_path": (paths.to_relative(outcome["raw_xacro_dest"])
                           if outcome["raw_xacro_dest"] else None),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "notes": source.notes,
    })
    flag = " (flagged, to revisit)" if license_status == "no-license" else ""
    print(f"[{source.robot_id}] collected -- license: {license_status}{flag}")
    if license_status == "no-license":
        report.warn(source.robot_id, kind=source.robot_class or "urdf",
                    reason="collected WITHOUT a declared license, on an "
                           "explicit project decision (ALLOW_NO_LICENSE_FOR)")
    report.ok(source.robot_id, kind=source.robot_class or "urdf",
              detail=f"{source.source_type.value} — license {license_status}")


def main() -> None:
    report = RunReport("cat3-collect", category=CATEGORY,
                       title="Category 3 — phase 1 (URDF collection)")
    print(f"Project root : {paths.PROJECT_ROOT}")
    print(f"Raw output   : {RAW_URDF_DIR}\n")
    paths.ensure_dirs(RAW_URDF_DIR, METADATA_PATH.parent, GIT_CACHE_DIR)
    report.info("Catalogue", f"{len(PILOT_CATALOG)} robots")
    report.info("Raw output", f"`{paths.to_relative(RAW_URDF_DIR)}`")
    report.info("Tolerated no-license", sorted(ALLOW_NO_LICENSE_FOR) or "none")

    if METADATA_PATH.exists():
        METADATA_PATH.unlink()

    for source in PILOT_CATALOG:
        try:
            _collect_one(source, report)
        except Exception as exc:  # noqa: BLE001 -- keep going with the others
            print(f"[{source.robot_id}] FAILED: {exc}")
            report.fail(source.robot_id, kind=source.robot_class or "urdf", exc=exc)
            # A failure used to leave an empty directory behind,
            # indistinguishable from a successful collection on disk.
            if _cleanup_if_empty(_robot_dir(source)):
                print(f"[{source.robot_id}] empty directory removed")

    report_path = report.write()
    counts = report.counts()
    print(f"\nDone: {counts['ok']} collected, {counts['skip']} set aside, "
          f"{counts['fail']} failed out of {len(PILOT_CATALOG)}.")
    print(f"Metadata : {METADATA_PATH}")
    print(f"Report   : {report_path}")


if __name__ == "__main__":
    main()
