"""
Récupération directe depuis un dépôt git, utilisée pour les robots absents
du catalogue de robot_descriptions.py (ex: AgileX Ranger Mini).

Utilise un clone superficiel (--depth 1) en sparse-checkout pour ne
récupérer que le sous-dossier nécessaire : rapide et peu gourmand en
bande passante, même sur un dépôt volumineux (meshes binaires inclus).
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitFetchResult:
    repo_root: Path
    file_path: Path


def fetch_from_git(
    repo_url: str,
    ref: str,
    file_path_in_repo: str,
    cache_root: Path,
) -> GitFetchResult:
    repo_name = repo_url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[: -len(".git")]
    target_dir = cache_root / repo_name

    if not target_dir.exists():
        subprocess.run(
            [
                "git", "clone", "--depth", "1", "--filter=blob:none",
                "--sparse", "--branch", ref, repo_url, str(target_dir),
            ],
            check=True, capture_output=True, text=True,
        )
        sparse_dir = str(Path(file_path_in_repo).parent)
        subprocess.run(
            ["git", "sparse-checkout", "set", sparse_dir],
            cwd=target_dir, check=True, capture_output=True, text=True,
        )

    file_path = target_dir / file_path_in_repo
    if not file_path.exists():
        raise FileNotFoundError(f"{file_path_in_repo} introuvable dans {repo_url}")

    return GitFetchResult(repo_root=target_dir, file_path=file_path)
