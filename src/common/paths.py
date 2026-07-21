"""
Project paths -- single source of truth.

Every script imports its paths from here: no more relative paths such as
"../../data/...", so scripts run from any working directory.

The project root is auto-detected from the location of this file
(src/common/paths.py -> two levels up). It can be forced with the
HERMES_ROOT environment variable, useful in CI or when the project is
mounted elsewhere:

    export HERMES_ROOT=/home/tiago/HermesPerso/HermesLLM

Data layout (identical for cat1 / cat2 / cat3):

    data/<cat>/
        raw/<kind>/<item_id>/...     raw files, by nature of source
                                     (cat1: docs|code|interfaces|notebooks,
                                      cat2: docs|code|papers,
                                      cat3: urdf|manuals)
        raw/_cache/git/              git clones (never part of the corpus)
        metadata/collection_metadata.jsonl
        clean/corpus_clean.jsonl
        clean/corpus_stats.md

    data/full/                       the merged deliverable

The <kind> level is what makes the layout reusable: each category declares
its own natures of source without changing a line of this module.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_ROOT_VAR = "HERMES_ROOT"


def _detect_root() -> Path:
    forced = os.environ.get(ENV_ROOT_VAR)
    if forced:
        return Path(forced).expanduser().resolve()
    # src/common/paths.py -> parents[0]=common, [1]=src, [2]=project root
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT: Path = _detect_root()
SRC_DIR: Path = PROJECT_ROOT / "src"
DATA_DIR: Path = PROJECT_ROOT / "data"
LOGS_DIR: Path = PROJECT_ROOT / "logs"

# Known categories (for cross-category scripts / global stats)
CATEGORIES = ("cat1", "cat2", "cat3")


# --------------------------------------------------------------------------
# Per-category paths -- generic, valid for cat1/cat2/cat3
# --------------------------------------------------------------------------

def category_dir(category: str) -> Path:
    return DATA_DIR / category


def raw_dir(category: str) -> Path:
    return category_dir(category) / "raw"


def raw_kind_dir(category: str, kind: str) -> Path:
    """Raw files of a given nature: cat3 -> kind='urdf' or 'manuals'."""
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
# Merged corpus (the three categories combined)
#
# Lives next to the categories, never inside one of them: it is a DERIVED,
# regenerable deliverable, and the per-category corpora remain the source
# of truth.
# --------------------------------------------------------------------------

def full_dir() -> Path:
    return DATA_DIR / "full"


def full_corpus_path() -> Path:
    return full_dir() / "corpus_full.jsonl"


def full_stats_path() -> Path:
    return full_dir() / "corpus_full_stats.md"


# --------------------------------------------------------------------------
# Run logs (Markdown reports) -- shared across categories
# --------------------------------------------------------------------------

def logs_dir() -> Path:
    return LOGS_DIR


def report_path(name: str, stamp: str) -> Path:
    """
    Path of a run report: logs/<stamp>-<name>.md
    `stamp` is supplied by the caller (common.run_report) so that every
    file of a given run shares the same timestamp.
    """
    return LOGS_DIR / f"{stamp}-{name}.md"


# --------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------

def ensure_dirs(*paths: Path) -> None:
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def to_relative(path: Path) -> str:
    """
    Path relative to the project root, for STORAGE in metadata. We never
    store absolute paths in the JSONL files: the project stays movable from
    one machine to another.
    """
    p = Path(path).resolve()
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


def from_relative(stored: str) -> Path:
    """Inverse of to_relative: re-absolutise a path read from a JSONL."""
    p = Path(stored)
    return p if p.is_absolute() else (PROJECT_ROOT / p)


def bootstrap_sys_path() -> None:
    """
    Add src/ to sys.path so that 'common.*' and 'cat3.*' are importable
    when a script is run directly (python3 build_corpus.py) from any
    working directory.
    """
    import sys
    s = str(SRC_DIR)
    if s not in sys.path:
        sys.path.insert(0, s)


if __name__ == "__main__":
    print(f"{ENV_ROOT_VAR:14s} = {os.environ.get(ENV_ROOT_VAR) or '(unset, auto-detected)'}")
    print(f"{'PROJECT_ROOT':14s} = {PROJECT_ROOT}")
    print(f"{'exists?':14s} = {PROJECT_ROOT.exists()}")
    for cat in CATEGORIES:
        print(f"\n[{cat}]")
        for label, p in [("raw", raw_dir(cat)),
                         ("git cache", git_cache_dir(cat)),
                         ("metadata", metadata_path(cat)),
                         ("corpus", corpus_path(cat)),
                         ("stats", stats_path(cat))]:
            print(f"  {label:12s} {p}   {'[ok]' if p.exists() else ''}")
    print("\n[full]")
    for label, p in [("corpus", full_corpus_path()), ("stats", full_stats_path())]:
        print(f"  {label:12s} {p}   {'[ok]' if p.exists() else ''}")
