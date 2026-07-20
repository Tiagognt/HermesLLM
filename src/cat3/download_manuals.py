"""
Aide au téléchargement MANUEL des manuels PDF.

Ce script ne télécharge pas à votre place (les sites fabricants exigent
souvent un navigateur / une connexion). Il :
  1. crée l'arborescence data/cat3/manuals/<robot_id>/,
  2. imprime une checklist (robot, document, URL, chemin cible, licence),
  3. indique lesquels sont déjà présents.

Placez chaque PDF téléchargé sous data/cat3/manuals/<robot_id>/manual.pdf
(ou le target_filename indiqué), puis lancez build_corpus.py.

Usage :
    python3 download_manuals.py            # checklist + création des dossiers
    python3 download_manuals.py --check    # ne fait que vérifier la présence
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MANIFEST = Path(__file__).with_name("pdf_manifest.json")
MANUALS_DIR = Path("../../data/cat3/manuals")


def load_manifest() -> list:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["manuals"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="vérifier la présence seulement")
    args = ap.parse_args()

    manuals = load_manifest()
    present = 0
    print(f"{'robot_id':24s} {'présent':8s} document / URL / licence")
    print("-" * 100)
    for m in manuals:
        robot_dir = MANUALS_DIR / m["robot_id"]
        if not args.check:
            robot_dir.mkdir(parents=True, exist_ok=True)
        target = robot_dir / m["target_filename"]
        ok = target.exists()
        present += ok
        flag = "OUI" if ok else "—"
        print(f"{m['robot_id']:24s} {flag:8s} {m['document']}")
        print(f"{'':33s} URL : {m['url']}")
        print(f"{'':33s} cible : {target}")
        print(f"{'':33s} licence : {m['license_note']}")
    print("-" * 100)
    print(f"{present}/{len(manuals)} manuels présents. "
          f"Déposez les PDF manquants aux chemins 'cible' ci-dessus.")


if __name__ == "__main__":
    main()
