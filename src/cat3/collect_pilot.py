"""
Point d'entrée du pilote de collecte (catégorie 3 -- URDF & Robot Specs).

Pour chaque robot du catalogue (sources.py) :
  1. récupère le fichier source (via robot_descriptions.py ou git direct)
  2. si c'est un Xacro, le rend en URDF (xacro_render.py)
  3. classe la licence selon les règles des consignes (license_utils.py)
  4. copie le(s) fichier(s) bruts dans data/raw/<robot_id>/
  5. ajoute une ligne dans data/collection_metadata.jsonl

Ce script NE fait PAS la transformation vers le corpus final (parsing des
capacités, génération de la description en langage naturel, JSONL final).
C'est l'étape suivante, volontairement séparée -- ce module ne produit que
des fichiers bruts + métadonnées de provenance/licence.

Usage :
    python3 collect_pilot.py
"""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fetch_git_source import fetch_from_git
from fetch_robot_descriptions import fetch_via_robot_descriptions
from license_utils import classify_license, is_collectible
from sources import PILOT_CATALOG, RobotSource, SourceType
from xacro_render import render_xacro_to_urdf

RAW_DATA_DIR = Path("../../data/cat3/raw")
METADATA_PATH = Path("../../data/cat3/collection_metadata.jsonl")
GIT_CACHE_DIR = Path("../../data/cat3/raw/_git_cache")

# Robots pour lesquels une absence de licence est explicitement acceptée
# (décision projet du 2026-07-15, à traiter plus tard -- cf. sources.py).
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


def _collect_one(source: RobotSource) -> None:
    print(f"[{source.robot_id}] collecte en cours...")
    robot_dir = RAW_DATA_DIR / source.robot_id
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
        print(f"[{source.robot_id}] ECARTE -- licence non conforme ({license_status})")
        shutil.rmtree(robot_dir, ignore_errors=True)
        return

    _write_metadata_row({
        "robot_id": source.robot_id,
        "display_name": source.display_name,
        "fleet_priority": source.fleet_priority,
        "source_type": source.source_type.value,
        "repo_url": outcome["repo_url"],
        "repo_ref": outcome["repo_ref"],
        "source_file": outcome["source_file"],
        "license_status": license_status,
        "raw_urdf_path": str(outcome["raw_urdf_dest"]),
        "raw_xacro_path": str(outcome["raw_xacro_dest"]) if outcome["raw_xacro_dest"] else None,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "notes": source.notes,
    })
    flag = " (flagué, à traiter)" if license_status == "no-license" else ""
    print(f"[{source.robot_id}] collecté -- licence: {license_status}{flag}")


def main() -> None:
    if METADATA_PATH.exists():
        METADATA_PATH.unlink()

    for source in PILOT_CATALOG:
        try:
            _collect_one(source)
        except Exception as exc:  # noqa: BLE001 -- on veut continuer les autres robots
            print(f"[{source.robot_id}] ECHEC: {exc}")

    print(f"\nTerminé. Résumé dans {METADATA_PATH}")


if __name__ == "__main__":
    main()
