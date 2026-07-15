"""
Récupération via la bibliothèque robot_descriptions.py.

Cette bibliothèque gère elle-même :
  - le clone et le cache local du dépôt source,
  - le rendu Xacro -> URDF de façon transparente si la description déclare
    un XACRO_PATH plutôt qu'un URDF_PATH direct,
  - le rattachement de la licence déclarée (license_spdx) et du dépôt
    d'origine (avec commit figé, pour la reproductibilité).
"""

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from robot_descriptions._descriptions import DESCRIPTIONS
from robot_descriptions._repositories import REPOSITORIES


@dataclass
class FetchResult:
    urdf_path: Path
    xacro_path: Optional[Path]     # renseigné seulement si la source est un Xacro
    repo_url: str
    repo_commit: str
    license_spdx: Optional[str]
    maker: str
    robot_name: str


def fetch_via_robot_descriptions(description_module: str) -> FetchResult:
    """
    description_module: nom du module tel qu'utilisé par robot_descriptions,
    ex. "g1_description", "go2_description".
    """
    mod = importlib.import_module(f"robot_descriptions.{description_module}")

    urdf_path = Path(getattr(mod, "URDF_PATH"))
    xacro_path_raw = getattr(mod, "XACRO_PATH", None)
    xacro_path = Path(xacro_path_raw) if xacro_path_raw else None

    meta = DESCRIPTIONS[description_module]
    repo = REPOSITORIES[meta.repository]

    return FetchResult(
        urdf_path=urdf_path,
        xacro_path=xacro_path,
        repo_url=repo.url,
        repo_commit=repo.commit,
        license_spdx=meta.license_spdx,
        maker=meta.maker,
        robot_name=meta.robot,
    )
