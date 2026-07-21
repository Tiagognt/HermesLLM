"""
Récupération de dépôts git complets -- transverse cat1 / cat2.

cat3 récupérait UN fichier par robot (`cat3/fetch_git_source.py`, clone
sparse). cat1 a besoin de l'inverse : des arborescences entières de
documentation. D'où ce module, générique et réutilisable par cat2.

Choix : clone *shallow* (`--depth 1`) sur une référence donnée, puis
relevé du commit obtenu. Le commit est stocké dans les métadonnées, ce qui
rend la collecte auditable même si la branche bouge ensuite.

Le module lit aussi le fichier de licence du dépôt et tente de
l'identifier. Cette identification sert de CONTRE-VÉRIFICATION du SPDX
déclaré à la main dans le catalogue : c'est le catalogue qui fait foi
(vérifié par un humain), mais un désaccord est signalé plutôt que tu.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

LICENSE_FILENAMES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENSE.TXT",
                     "LICENCE", "COPYING", "COPYING.txt", "LICENSE-APACHE")

# Signatures textuelles -> identifiant SPDX. Ordre significatif : les
# motifs les plus spécifiques d'abord.
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
            f"échec de `{' '.join(cmd[:4])}...` : {proc.stderr.strip()[:300]}")
    return proc.stdout.strip()


def detect_license(repo_path: Path) -> tuple:
    """Retourne (chemin_du_fichier, spdx_detecté_ou_None)."""
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
        return candidate, None      # fichier présent mais non reconnu
    return None, None


def clone(source_id: str, repo_url: str, ref: str, cache_root: Path,
          *, refresh: bool = False,
          sparse_paths: Optional[List[str]] = None) -> RepoCheckout:
    """
    Clone shallow dans cache_root/<source_id>. Si le dossier existe déjà et
    que refresh=False, on le réutilise tel quel : re-cloner 20 dépôts à
    chaque essai est inutile et fragile côté réseau.

    sparse_paths : ne matérialiser que ces sous-arbres. Indispensable pour
    les dépôts monolithiques -- `google-research` fait plusieurs Go, mais
    5 Mo en sparse sur le seul dossier qui nous intéresse.
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
        warnings.append("aucun fichier LICENSE à la racine du dépôt")
    elif detected is None:
        warnings.append(f"fichier {license_file.name} présent mais licence "
                        f"non reconnue automatiquement")

    return RepoCheckout(
        source_id=source_id, path=dest, repo_url=repo_url, ref=ref,
        commit=commit, license_file=license_file, detected_license=detected,
        warnings=warnings,
    )


def select_files(root: Path, include_globs: List[str],
                 exclude_globs: Optional[List[str]] = None) -> List[Path]:
    """
    Fichiers retenus, chemins ABSOLUS, triés -- l'ordre doit être
    déterministe pour que deux collectes donnent le même corpus.
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
