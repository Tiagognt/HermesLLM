"""
Point d'entrée de la PHASE 1 (collecte) -- catégorie 1 (General Robot Data).

Pour chaque source du catalogue (`sources.py`) :
  1. clone shallow du dépôt sur une référence donnée (sparse si nécessaire)
  2. lecture du fichier LICENSE et CONTRE-VÉRIFICATION du SPDX déclaré
  3. barrière licence (license_utils)
  4. sélection des fichiers par globs, copie dans
     data/cat1/raw/<kind>/<source_id>/<chemin_relatif>
  5. une ligne dans data/cat1/metadata/collection_metadata.jsonl

Comme en cat3, ce script NE transforme rien : c'est `build_corpus.py`
(phase 2) qui produit le corpus. On doit pouvoir régénérer le corpus, et
notamment rejouer les quotas de tokens, sans re-cloner 20 dépôts.

Lançable depuis n'importe quel répertoire :
    python3 /chemin/vers/src/cat1/collect_docs.py
    python3 .../collect_docs.py --only ros2_documentation,nav2_docs
    python3 .../collect_docs.py --refresh        # re-clone au lieu du cache
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

# Aucune source cat1 n'est collectée sans licence : contrairement à cat3
# (manuels constructeur déposés à la main), tout est ici du contenu public
# dont la licence est vérifiable. L'ensemble reste vide volontairement.
ALLOW_NO_LICENSE_FOR: set = set()


def _write_metadata_row(row: dict) -> None:
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with METADATA_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _drop_metadata_rows(source_ids: set) -> int:
    """
    Retire des métadonnées les lignes des sources sur le point d'être
    recollectées. Sans cela, `--only` AJOUTE une seconde ligne pour la même
    source, la phase 2 adapte deux fois les mêmes fichiers, et le
    dédoublonneur écarte tout le second passage.
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
    """Copie en préservant l'arborescence relative (utile pour la diversité)."""
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
    print(f"[{source.source_id}] clonage ({source.repo_url} @ {source.repo_ref})...")
    checkout = clone(source.source_id, source.repo_url, source.repo_ref,
                     GIT_CACHE_DIR, refresh=refresh,
                     sparse_paths=source.sparse_paths)

    # -- contre-vérification de la licence ---------------------------------
    # Le catalogue fait foi (vérification humaine), mais tout désaccord avec
    # le fichier LICENSE réel doit remonter : c'est exactement le genre
    # d'écart qui, non signalé, finit par polluer le corpus.
    for w in checkout.warnings:
        report.warn(source.source_id, kind=source.kind,
                    reason=f"licence : {w} (déclaré au catalogue : "
                           f"{source.license_spdx})")
    if (checkout.detected_license
            and checkout.detected_license != source.license_spdx):
        report.warn(
            source.source_id, kind=source.kind,
            reason=f"DÉSACCORD de licence : catalogue={source.license_spdx}, "
                   f"détecté dans {checkout.license_file.name if checkout.license_file else '?'}"
                   f"={checkout.detected_license}. Le catalogue prime ; à "
                   f"trancher à la main.")

    license_status = classify_license(source.license_spdx)
    if not is_collectible(license_status,
                          allow_no_license_override=source.source_id in ALLOW_NO_LICENSE_FOR):
        print(f"[{source.source_id}] ECARTE -- licence non conforme ({license_status})")
        report.skip(source.source_id, kind=source.kind,
                    reason=f"licence non conforme ({license_status})")
        return

    # -- sélection et copie -------------------------------------------------
    files = select_files(checkout.path, source.include_globs, source.exclude_globs)
    if not files:
        # Un glob qui ne ramène rien est presque toujours une erreur de
        # catalogue (branche ou arborescence changée) : jamais silencieux.
        report.fail(source.source_id, kind=source.kind,
                    reason=f"aucun fichier ne correspond aux globs "
                           f"{source.include_globs} dans {checkout.path.name} "
                           f"(branche {source.repo_ref}) — catalogue à corriger")
        print(f"[{source.source_id}] AUCUN FICHIER SELECTIONNE")
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
    print(f"[{source.source_id}] collecté -- {n_files} fichiers, "
          f"{n_bytes/1e6:.2f} Mo, licence {license_status}")
    report.ok(source.source_id, kind=source.kind,
              detail=f"{n_files} fichiers, {n_bytes/1e6:.2f} Mo, "
                     f"licence {license_status}, commit {checkout.commit[:8]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 1 -- collecte cat1")
    ap.add_argument("--only", default=None,
                    help="restreindre à ces source_id (séparés par des virgules)")
    ap.add_argument("--refresh", action="store_true",
                    help="re-cloner les dépôts au lieu de réutiliser le cache")
    args = ap.parse_args()

    selection = CATALOG
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        selection = [s for s in CATALOG if s.source_id in wanted]
        unknown = wanted - {s.source_id for s in CATALOG}
        if unknown:
            raise SystemExit(f"source_id inconnu(s) : {sorted(unknown)}")

    report = RunReport("cat1-collect", category=CATEGORY,
                       title="Catégorie 1 — phase 1 (collecte des sources)")
    print(f"Racine projet : {paths.PROJECT_ROOT}")
    print(f"Cache git     : {GIT_CACHE_DIR}")
    print(f"Sources       : {len(selection)} / {len(CATALOG)}")
    print(f"Budget total  : {total_budget():,} tokens (plafonds phase 2)\n")
    report.info("Sources traitées", f"{len(selection)} / {len(CATALOG)}")
    report.info("Budget total déclaré", f"{total_budget():,} tokens")
    report.info("Cache git", f"`{paths.to_relative(GIT_CACHE_DIR)}`")

    paths.ensure_dirs(METADATA_PATH.parent, GIT_CACHE_DIR)
    if not args.only:
        if METADATA_PATH.exists():
            METADATA_PATH.unlink()
    else:
        n = _drop_metadata_rows({s.source_id for s in selection})
        if n:
            print(f"[metadonnees] {n} ligne(s) remplacee(s)\n")

    for source in selection:
        try:
            _collect_one(source, report, refresh=args.refresh)
        except Exception as exc:  # noqa: BLE001 -- une source cassée n'arrête rien
            print(f"[{source.source_id}] ECHEC: {exc}")
            report.fail(source.source_id, kind=source.kind, exc=exc)

    report_path = report.write()
    c = report.counts()
    print(f"\nTerminé : {c['ok']} collectées, {c['skip']} écartées, "
          f"{c['fail']} en échec sur {len(selection)}.")
    print(f"Métadonnées : {METADATA_PATH}")
    print(f"Rapport     : {report_path}")


if __name__ == "__main__":
    main()
