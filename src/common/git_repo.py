"""
Fetching whole git repositories -- shared by cat1 / cat2.

cat3 fetches ONE file per robot (`cat3/fetch_git_source.py`, sparse clone).
cat1 needs the opposite: entire documentation trees. Hence this module,
generic and reusable by cat2.

Design: shallow clone (`--depth 1`) on a given reference, then record the
resulting commit. The commit is stored in the metadata, which keeps the
collection auditable even if the branch moves afterwards.

The module also reads the repository's license file and tries to identify
it. That identification is a CROSS-CHECK of the SPDX id declared by hand in
the catalogue: the catalogue is authoritative (a human verified it), but a
disagreement is reported rather than silently ignored.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

LICENSE_FILENAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENSE.TXT",
                     "LICENCE", "COPYING", "COPYING.txt", "LICENSE-APACHE")

# Textual signatures -> SPDX identifier. Order matters: the most specific
# patterns come first.
_LICENSE_SIGNATURES = [
    (re.compile(r"GNU LESSER GENERAL PUBLIC LICENSE", re.I), "LGPL"),
    (re.compile(r"GNU GENERAL PUBLIC LICENSE", re.I), "GPL"),
    (re.compile(r"Apache License[\s,]*Version 2\.0", re.I), "Apache-2.0"),
    (re.compile(r"MIT License|Permission is hereby granted, free of charge", re.I), "MIT"),
    (re.compile(r"Creative Commons Attribution 4\.0", re.I), "CC-BY-4.0"),
    (re.compile(r"Creative Commons Attribution 3\.0", re.I), "CC-BY-3.0"),
    (re.compile(r"NVIDIA (Source Code )?License", re.I), "NVIDIA-Proprietary"),
    (re.compile(r"Mozilla Public License", re.I), "MPL"),
]

_BSD_BODY = re.compile(r"Redistribution and use in source and binary forms", re.I)
_BSD_THIRD_CLAUSE = re.compile(r"Neither the name", re.I)


@dataclass
class RepoCheckout:
    source_id: str
    path: Path
    repo_url: str
    ref: str
    commit: str
    license_file: Optional[Path] = None
    detected_license: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


def _run(cmd: List[str], cwd: Optional[Path] = None, timeout: int = 900) -> str:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(
            f"`{' '.join(cmd[:4])}...` failed: {proc.stderr.strip()[:300]}")
    return proc.stdout.strip()


def detect_license(repo_path: Path) -> tuple:
    """Returns (license_file_path, detected_spdx_or_None)."""
    for name in LICENSE_FILENAMES:
        candidate = repo_path / name
        if not candidate.is_file():
            continue
        head = candidate.read_text(encoding="utf-8", errors="replace")[:8000]
        for pattern, spdx in _LICENSE_SIGNATURES:
            if pattern.search(head):
                return candidate, spdx
        if _BSD_BODY.search(head):
            return candidate, ("BSD-3-Clause" if _BSD_THIRD_CLAUSE.search(head)
                               else "BSD-2-Clause")
        return candidate, None      # file present but not recognised
    return None, None


def clone(source_id: str, repo_url: str, ref: str, cache_root: Path,
          *, refresh: bool = False,
          sparse_paths: Optional[List[str]] = None) -> RepoCheckout:
    """
    Shallow clone into cache_root/<source_id>. If the directory already
    exists and refresh=False, it is reused as-is: re-cloning 25 repositories
    on every attempt is wasteful and network-fragile.

    sparse_paths: materialise only these subtrees. Essential for monolithic
    repositories -- `google-research` is several GB, but 5 MB sparse on the
    single directory we care about.
    """
    cache_root.mkdir(parents=True, exist_ok=True)
    dest = cache_root / source_id

    if dest.exists() and refresh:
        import shutil
        shutil.rmtree(dest, ignore_errors=True)

    if not dest.exists():
        if sparse_paths:
            _run(["git", "clone", "--quiet", "--depth", "1",
                  "--filter=blob:none", "--sparse",
                  "--branch", ref, "--single-branch", repo_url, str(dest)])
            _run(["git", "sparse-checkout", "set", *sparse_paths], cwd=dest)
        else:
            _run(["git", "clone", "--quiet", "--depth", "1",
                  "--branch", ref, "--single-branch", repo_url, str(dest)])

    commit = _run(["git", "rev-parse", "HEAD"], cwd=dest)
    license_file, detected = detect_license(dest)

    warnings: List[str] = []
    if license_file is None:
        warnings.append("no LICENSE file at the repository root")
    elif detected is None:
        warnings.append(f"{license_file.name} present but the license was "
                        f"not recognised automatically")

    return RepoCheckout(
        source_id=source_id, path=dest, repo_url=repo_url, ref=ref,
        commit=commit, license_file=license_file, detected_license=detected,
        warnings=warnings,
    )


def select_files(root: Path, include_globs: List[str],
                 exclude_globs: Optional[List[str]] = None) -> List[Path]:
    """
    Selected files, ABSOLUTE paths, sorted -- the order must be
    deterministic so that two collections produce the same corpus.
    """
    exclude_globs = exclude_globs or []
    selected: set = set()
    for pattern in include_globs:
        for p in root.glob(pattern):
            if p.is_file():
                selected.add(p)

    kept = []
    for p in sorted(selected):
        rel = p.relative_to(root)
        if any(rel.match(x) or str(rel).startswith(x.rstrip("*").rstrip("/"))
               for x in exclude_globs):
            continue
        kept.append(p)
    return kept
