"""
Direct fetch from a git repository, used for robots absent from the
robot_descriptions.py catalogue (e.g. AgileX Ranger Mini).

Uses a shallow clone (--depth 1) with sparse-checkout so that only the
required subdirectory is materialised: fast and light on bandwidth even for
a large repository (binary meshes included).
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
        raise FileNotFoundError(f"{file_path_in_repo} not found in {repo_url}")

    return GitFetchResult(repo_root=target_dir, file_path=file_path)
