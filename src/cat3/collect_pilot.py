"""
Point d'entrée du pilote de collecte (catégorie 3 -- URDF & Robot Specs).

Pour chaque robot du catalogue (sources.py) :
  1. récupère le fichier source (via robot_descriptions.py ou git direct)
  2. si c'est un Xacro, le rend en URDF (xacro_render.py)
  3. classe la licence selon les règles des consignes (license_utils.py)
  4. copie le(s) fichier(s) bruts dans data/cat3/raw/urdf/<robot_id>/
  5. ajoute une ligne dans data/cat3/metadata/collection_metadata.jsonl

Ce script NE fait PAS la transformation vers le corpus final : c'est
build_corpus.py (phase 2), volontairement séparé. Ce module ne produit que
des fichiers bruts + métadonnées de provenance/licence.

Lançable depuis n'importe quel répertoire :
    python3 /chemin/vers/src/cat3/collect_pilot.py
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


def _robot_dir(source: RobotSource) -> Path:
    return RAW_URDF_DIR / source.robot_id


def _cleanup_if_empty(robot_dir: Path) -> bool:
    """
    Supprime le dossier d'un robot s'il est resté vide.

    Le dossier est créé avant la récupération ; si celle-ci échoue, il
    restait sur le disque, vide, et donnait l'illusion d'un robot collecté
    (cas réel : `tiago`, dossier vide et absent des métadonnées).
    """
    if robot_dir.is_dir() and not any(robot_dir.iterdir()):
        robot_dir.rmdir()
        return True
    return False


def _collect_one(source: RobotSource, report: RunReport) -> None:
    print(f"[{source.robot_id}] collecte en cours...")
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
        print(f"[{source.robot_id}] ECARTE -- licence non conforme ({license_status})")
        shutil.rmtree(robot_dir, ignore_errors=True)
        report.skip(source.robot_id, kind=source.robot_class or "urdf",
                    reason=f"licence non conforme ({license_status}) — "
                           f"bruts supprimés du disque"
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
        # Chemins RELATIFS à la racine du projet : les métadonnées restent
        # valides si le projet est déplacé ou cloné sur une autre machine.
        "raw_urdf_path": paths.to_relative(outcome["raw_urdf_dest"]),
        "raw_xacro_path": (paths.to_relative(outcome["raw_xacro_dest"])
                           if outcome["raw_xacro_dest"] else None),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "notes": source.notes,
    })
    flag = " (flagué, à traiter)" if license_status == "no-license" else ""
    print(f"[{source.robot_id}] collecté -- licence: {license_status}{flag}")
    if license_status == "no-license":
        report.warn(source.robot_id, kind=source.robot_class or "urdf",
                    reason="collecté SANS licence déclarée, sur décision "
                           "explicite du projet (ALLOW_NO_LICENSE_FOR)")
    report.ok(source.robot_id, kind=source.robot_class or "urdf",
              detail=f"{source.source_type.value} — licence {license_status}")


def main() -> None:
    report = RunReport("cat3-collect", category=CATEGORY,
                       title="Catégorie 3 — phase 1 (collecte URDF)")
    print(f"Racine projet : {paths.PROJECT_ROOT}")
    print(f"Sortie brute  : {RAW_URDF_DIR}\n")
    paths.ensure_dirs(RAW_URDF_DIR, METADATA_PATH.parent, GIT_CACHE_DIR)
    report.info("Catalogue", f"{len(PILOT_CATALOG)} robots")
    report.info("Sortie brute", f"`{paths.to_relative(RAW_URDF_DIR)}`")
    report.info("no-license tolérés", sorted(ALLOW_NO_LICENSE_FOR) or "aucun")

    if METADATA_PATH.exists():
        METADATA_PATH.unlink()

    for source in PILOT_CATALOG:
        try:
            _collect_one(source, report)
        except Exception as exc:  # noqa: BLE001 -- on veut continuer les autres robots
            print(f"[{source.robot_id}] ECHEC: {exc}")
            report.fail(source.robot_id, kind=source.robot_class or "urdf", exc=exc)
            # Un échec laissait derrière lui un dossier vide, indistinguable
            # d'une collecte réussie à l'inspection du disque.
            if _cleanup_if_empty(_robot_dir(source)):
                print(f"[{source.robot_id}] dossier vide supprimé")

    report_path = report.write()
    counts = report.counts()
    print(f"\nTerminé : {counts['ok']} collectés, {counts['skip']} écartés, "
          f"{counts['fail']} en échec sur {len(PILOT_CATALOG)}.")
    print(f"Métadonnées : {METADATA_PATH}")
    print(f"Rapport     : {report_path}")


if __name__ == "__main__":
    main()
