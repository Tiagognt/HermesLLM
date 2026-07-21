"""
Aide au téléchargement MANUEL des manuels PDF.

Ce script ne télécharge pas à votre place (les sites fabricants exigent
souvent un navigateur / une connexion). Il :
  1. crée l'arborescence data/cat3/raw/manuals/<robot_id>/,
  2. imprime une checklist (robot, document, URL, licence),
  3. indique lesquels sont déjà présents ET sous quel nom de fichier.

N'IMPORTE quel nom de fichier .pdf est accepté dans le dossier du robot
(g1_manual.pdf, technical_manual.pdf...) : inutile de renommer.

Lançable depuis n'importe quel répertoire :
    python3 /chemin/vers/src/cat3/download_manuals.py
    python3 .../download_manuals.py --check     # vérifie sans rien créer
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
        raise SystemExit(f"Manifeste introuvable. Attendu : {MANIFEST_PATH}")
    if path is LEGACY_MANIFEST_PATH:
        print(f"[note] manifeste à l'ancien emplacement ({path}).")
        print(f"       Emplacement recommandé : {MANIFEST_PATH}\n")
    return json.loads(path.read_text(encoding="utf-8"))["manuals"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="vérifier la présence seulement")
    args = ap.parse_args()

    manuals = load_manifest()
    print(f"Racine projet : {paths.PROJECT_ROOT}")
    print(f"Dossier cible : {MANUALS_DIR}\n")

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

        mark = f"OUI ({found.name})" if found else "—"
        print(f"{rid:24s} {mark}")
        print(f"{'':24s}   {m['document']}")
        print(f"{'':24s}   URL      : {m['url']}")
        print(f"{'':24s}   dossier  : {robot_dir}")
        print(f"{'':24s}   licence  : {status}"
              f"{'  [override autorisé dans le manifeste]' if allowed else ''}")

    print("-" * 90)
    print(f"{present}/{len(manuals)} manuels présents sur le disque.")
    print(f"{collectible_now}/{len(manuals)} passeraient la barrière licence en l'état.")
    print("\nPour inclure des manuels propriétaires, au choix :")
    print("  - build_corpus.py --sources pdf --allow-proprietary-pdf   (décision globale)")
    print("  - \"allow_no_license\": true sur l'entrée du manifeste      (décision par robot)")


if __name__ == "__main__":
    main()
