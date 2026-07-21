"""
Point d'entrée de la PHASE 1 (collecte) -- catégorie 2 (HMRS Data).

Deux voies, une seule sortie :

  dépôts   clone shallow + contre-vérification de licence + sélection par
           globs, exactement comme cat1 (common/git_repo.py).
  articles téléchargement du texte intégral arXiv (HTML ou PDF), une fois,
           dans data/cat2/raw/papers/<arxiv_id>/paper.txt.

Comme pour les autres catégories, rien n'est transformé ici : la phase 2
doit pouvoir rejouer les quotas sans re-télécharger 43 articles.

Lançable depuis n'importe quel répertoire :
    python3 /chemin/vers/src/cat2/collect_hmrs.py
    python3 .../collect_hmrs.py --only repos     # ou: papers
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

# Aucune source cat2 n'est collectée sans licence.
ALLOW_NO_LICENSE_FOR: set = set()

# arXiv demande d'espacer les requêtes automatisées.
ARXIV_DELAY_S = 3.0


def _write_metadata_row(row: dict) -> None:
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with METADATA_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _drop_metadata_rows(source_ids: set) -> int:
    """
    Retire des métadonnées les lignes des sources sur le point d'être
    recollectées.

    Sans cela, une collecte partielle (`--only`) AJOUTE une seconde ligne
    pour la même source : la phase 2 adapte alors deux fois les mêmes
    fichiers, et le dédoublonneur écarte l'intégralité du second passage.
    Symptôme observé : « 141 candidats -> 0 uniques ».
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
# Voie dépôts
# --------------------------------------------------------------------------

def _collect_repo(source: RepoSource, report: RunReport, *, refresh: bool) -> None:
    print(f"[{source.source_id}] clonage ({source.repo_url} @ {source.repo_ref})...")
    checkout = clone(source.source_id, source.repo_url, source.repo_ref,
                     GIT_CACHE_DIR, refresh=refresh,
                     sparse_paths=source.sparse_paths)

    for w in checkout.warnings:
        report.warn(source.source_id, kind=source.kind,
                    reason=f"licence : {w} (déclaré au catalogue : "
                           f"{source.license_spdx})")
    if checkout.detected_license and checkout.detected_license != source.license_spdx:
        report.warn(source.source_id, kind=source.kind,
                    reason=f"DÉSACCORD de licence : catalogue="
                           f"{source.license_spdx}, détecté="
                           f"{checkout.detected_license}. Le catalogue prime ; "
                           f"à trancher à la main.")

    license_status = classify_license(source.license_spdx)
    if not is_collectible(license_status,
                          allow_no_license_override=source.source_id in ALLOW_NO_LICENSE_FOR):
        print(f"[{source.source_id}] ECARTE -- licence non conforme ({license_status})")
        report.skip(source.source_id, kind=source.kind,
                    reason=f"licence non conforme ({license_status})")
        return

    files = select_files(checkout.path, source.include_globs, source.exclude_globs)
    if not files:
        report.fail(source.source_id, kind=source.kind,
                    reason=f"aucun fichier ne correspond aux globs "
                           f"{source.include_globs} (branche {source.repo_ref}) "
                           f"— catalogue à corriger")
        print(f"[{source.source_id}] AUCUN FICHIER SELECTIONNE")
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
    print(f"[{source.source_id}] collecté -- {len(files)} fichiers, "
          f"{n_bytes/1e6:.2f} Mo, licence {license_status}")
    report.ok(source.source_id, kind=source.kind,
              detail=f"{len(files)} fichiers, {n_bytes/1e6:.2f} Mo, "
                     f"licence {license_status}, commit {checkout.commit[:8]}")


# --------------------------------------------------------------------------
# Voie articles
# --------------------------------------------------------------------------

def _collect_papers(report: RunReport, *, refresh: bool) -> None:
    license_status = classify_license(PAPER_LICENSE_SPDX)
    if not is_collectible(license_status):
        report.skip("(articles)", kind=KIND_PAPER,
                    reason=f"licence {license_status} non conforme")
        return

    tmp_dir = GIT_CACHE_DIR.parent / "arxiv_tmp"
    n_ok = 0
    for i, paper in enumerate(PAPER_CATALOG, start=1):
        dest_dir = PAPERS_DIR / paper.arxiv_id
        dest = dest_dir / "paper.txt"

        if dest.exists() and not refresh:
            text = dest.read_text(encoding="utf-8")
            print(f"  [{paper.arxiv_id}] déjà présent ({len(text)} car.)")
        else:
            try:
                result = fetch_arxiv.fetch(paper.arxiv_id, paper.fetch, tmp_dir)
            except Exception as exc:  # noqa: BLE001 -- un article ne bloque rien
                print(f"  [{paper.arxiv_id}] ECHEC : {exc}")
                report.fail(paper.arxiv_id, kind=KIND_PAPER, exc=exc)
                time.sleep(ARXIV_DELAY_S)
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest.write_text(result.text, encoding="utf-8")
            text = result.text
            print(f"  [{paper.arxiv_id}] {paper.fetch} -- {len(text)} car. "
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
            "license_detected": PAPER_LICENSE_SPDX,   # lu via OAI-PMH arXiv
            "raw_dir": paths.to_relative(dest_dir),
            "n_files": 1,
            "n_bytes": len(text.encode("utf-8")),
            # Budget porté par la famille entière, pas par article : les
            # articles se partagent un plafond commun en phase 2.
            "token_budget": PAPER_TOKEN_BUDGET,
            "url": paper.url,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "notes": f"arXiv {paper.arxiv_id}, licence CC-BY-4.0 vérifiée via "
                     f"OAI-PMH, texte intégral par voie {paper.fetch}",
        })
        n_ok += 1
        report.ok(paper.arxiv_id, kind=KIND_PAPER,
                  detail=f"{len(text)} caractères, voie {paper.fetch}")

    shutil.rmtree(tmp_dir, ignore_errors=True)
    print(f"\n  articles collectés : {n_ok}/{len(PAPER_CATALOG)}")


# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 1 -- collecte cat2")
    ap.add_argument("--only", default=None, choices=["repos", "papers"],
                    help="ne traiter qu'une des deux voies")
    ap.add_argument("--refresh", action="store_true",
                    help="re-cloner / re-télécharger au lieu du cache")
    args = ap.parse_args()

    report = RunReport("cat2-collect", category=CATEGORY,
                       title="Catégorie 2 — phase 1 (collecte HMRS)")
    print(f"Racine projet : {paths.PROJECT_ROOT}")
    print(f"Dépôts        : {len(REPO_CATALOG)}")
    print(f"Articles      : {len(PAPER_CATALOG)} (tous CC-BY-4.0)")
    print(f"Budget total  : {total_budget():,} tokens (plafonds phase 2)\n")
    report.info("Dépôts", len(REPO_CATALOG))
    report.info("Articles arXiv", f"{len(PAPER_CATALOG)} (tous CC-BY-4.0)")
    report.info("Budget total déclaré", f"{total_budget():,} tokens")

    paths.ensure_dirs(METADATA_PATH.parent, GIT_CACHE_DIR, PAPERS_DIR)
    if args.only is None:
        if METADATA_PATH.exists():
            METADATA_PATH.unlink()
    else:
        affected = ({s.source_id for s in REPO_CATALOG} if args.only == "repos"
                    else {f"arxiv-{p.arxiv_id}" for p in PAPER_CATALOG})
        n = _drop_metadata_rows(affected)
        if n:
            print(f"[metadonnees] {n} ligne(s) remplacee(s) pour la voie "
                  f"'{args.only}'\n")

    if args.only in (None, "repos"):
        for source in REPO_CATALOG:
            try:
                _collect_repo(source, report, refresh=args.refresh)
            except Exception as exc:  # noqa: BLE001
                print(f"[{source.source_id}] ECHEC: {exc}")
                report.fail(source.source_id, kind=source.kind, exc=exc)

    if args.only in (None, "papers"):
        print("\n--- articles arXiv ---")
        _collect_papers(report, refresh=args.refresh)

    report_path = report.write()
    c = report.counts()
    print(f"\nTerminé : {c['ok']} collectées, {c['skip']} écartées, "
          f"{c['fail']} en échec.")
    print(f"Métadonnées : {METADATA_PATH}")
    print(f"Rapport     : {report_path}")


if __name__ == "__main__":
    main()
