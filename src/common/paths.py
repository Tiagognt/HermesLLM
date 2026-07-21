"""
Chemins du projet -- source unique de vérité.

Tous les scripts importent leurs chemins d'ici : plus aucun chemin relatif
du type "../../data/...", donc les scripts se lancent depuis n'importe où.

La racine du projet est détectée automatiquement à partir de
l'emplacement de ce fichier (src/common/paths.py -> deux niveaux au-dessus).
Elle peut être forcée par la variable d'environnement HERMES_ROOT, utile
en CI ou si le projet est monté ailleurs :

    export HERMES_ROOT=/home/tiago/HermesPerso/HermessLLM

Arborescence des données (identique pour cat1 / cat2 / cat3) :

    data/<cat>/
        raw/<kind>/<item_id>/...     bruts par nature de source
                                     (cat3 : kind = "urdf" | "manuals")
        raw/_cache/git/              clones git (jamais dans le corpus)
        metadata/collection_metadata.jsonl
        clean/corpus_clean.jsonl
        clean/corpus_stats.md

Le niveau <kind> est ce qui rend l'arborescence réutilisable : cat1 et
cat2 auront leurs propres natures de sources (ex. "papers", "html",
"code") sans changer une ligne de ce module.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_ROOT_VAR = "HERMES_ROOT"


def _detect_root() -> Path:
    forced = os.environ.get(ENV_ROOT_VAR)
    if forced:
        return Path(forced).expanduser().resolve()
    # src/common/paths.py -> parents[0]=common, [1]=src, [2]=racine projet
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT: Path = _detect_root()
SRC_DIR: Path = PROJECT_ROOT / "src"
DATA_DIR: Path = PROJECT_ROOT / "data"
LOGS_DIR: Path = PROJECT_ROOT / "logs"

# Catégories connues (pour les scripts transverses / stats globales)
CATEGORIES = ("cat1", "cat2", "cat3")


# --------------------------------------------------------------------------
# Chemins par catégorie -- génériques, valables pour cat1/cat2/cat3
# --------------------------------------------------------------------------

def category_dir(category: str) -> Path:
    return DATA_DIR / category


def raw_dir(category: str) -> Path:
    return category_dir(category) / "raw"


def raw_kind_dir(category: str, kind: str) -> Path:
    """Bruts d'une nature donnée : cat3 -> kind='urdf' ou 'manuals'."""
    return raw_dir(category) / kind


def item_dir(category: str, kind: str, item_id: str) -> Path:
    return raw_kind_dir(category, kind) / item_id


def git_cache_dir(category: str) -> Path:
    return raw_dir(category) / "_cache" / "git"


def metadata_dir(category: str) -> Path:
    return category_dir(category) / "metadata"


def metadata_path(category: str) -> Path:
    return metadata_dir(category) / "collection_metadata.jsonl"


def clean_dir(category: str) -> Path:
    return category_dir(category) / "clean"


def corpus_path(category: str) -> Path:
    return clean_dir(category) / "corpus_clean.jsonl"


def stats_path(category: str) -> Path:
    return clean_dir(category) / "corpus_stats.md"


def code_dir(category: str) -> Path:
    return SRC_DIR / category


# --------------------------------------------------------------------------
# Journaux d'exécution (rapports .md) -- transverse aux catégories
# --------------------------------------------------------------------------

def logs_dir() -> Path:
    return LOGS_DIR


def report_path(name: str, stamp: str) -> Path:
    """
    Chemin d'un rapport d'exécution : logs/<stamp>-<name>.md
    stamp est fourni par l'appelant (common.run_report) pour que tous les
    fichiers d'un même run partagent le même horodatage.
    """
    return LOGS_DIR / f"{stamp}-{name}.md"


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------

def ensure_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def to_relative(path: Path) -> str:
    """
    Chemin relatif à la racine du projet, pour STOCKAGE dans les métadonnées.
    On ne stocke jamais d'absolu dans les JSONL : le projet reste déplaçable
    d'une machine à l'autre.
    """
    p = Path(path).resolve()
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


def from_relative(stored: str) -> Path:
    """Inverse de to_relative : re-absolutise un chemin lu dans un JSONL."""
    p = Path(stored)
    return p if p.is_absolute() else (PROJECT_ROOT / p)


def bootstrap_sys_path() -> None:
    """
    Ajoute src/ au sys.path pour que 'common.*' et 'cat3.*' soient
    importables quand un script est lancé directement (python3 build_corpus.py)
    depuis n'importe quel répertoire courant.
    """
    import sys
    s = str(SRC_DIR)
    if s not in sys.path:
        sys.path.insert(0, s)


if __name__ == "__main__":
    print(f"{ENV_ROOT_VAR:14s} = {os.environ.get(ENV_ROOT_VAR) or '(non défini, auto-détection)'}")
    print(f"{'PROJECT_ROOT':14s} = {PROJECT_ROOT}")
    print(f"{'existe ?':14s} = {PROJECT_ROOT.exists()}")
    for cat in CATEGORIES:
        print(f"\n[{cat}]")
        for label, p in [("raw urdf", raw_kind_dir(cat, "urdf")),
                         ("raw manuals", raw_kind_dir(cat, "manuals")),
                         ("git cache", git_cache_dir(cat)),
                         ("metadata", metadata_path(cat)),
                         ("corpus", corpus_path(cat)),
                         ("stats", stats_path(cat))]:
            print(f"  {label:12s} {p}   {'[ok]' if p.exists() else ''}")
