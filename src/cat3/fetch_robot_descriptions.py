"""
Récupération via la bibliothèque robot_descriptions.py.

Cette bibliothèque gère elle-même le clone, le cache local du dépôt
source, et le rattachement de la licence déclarée (license_spdx) + du
dépôt d'origine (avec commit figé, pour la reproductibilité).

En revanche elle N'expose PAS toujours un URDF prêt à l'emploi : environ
un module sur six ne fournit qu'un XACRO_PATH (Franka FER/FR3, UR5e/UR10e,
Kinova Gen3, xArm6/7...). Pour ces cas, on rend nous-mêmes le Xacro en
URDF via xacro_render.py, en transmettant les XACRO_ARGS que la
bibliothèque déclare (ex. UR : {"ur_type": "ur5e", "name": "ur5e"} ;
sans eux, xacro échoue avec "Undefined substitution argument"). Le
résultat rendu est mis en cache à côté du Xacro source, de sorte que
FetchResult.urdf_path pointe toujours vers un URDF valide -- le reste du
pipeline (collect_pilot) n'a donc pas à savoir si un rendu a eu lieu.
"""

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from robot_descriptions._descriptions import DESCRIPTIONS
from robot_descriptions._repositories import REPOSITORIES

from xacro_render import render_xacro_to_urdf


@dataclass
class FetchResult:
    urdf_path: Path
    xacro_path: Optional[Path]     # renseigné seulement si la source est un Xacro
    repo_url: str
    repo_commit: str
    license_spdx: Optional[str]
    maker: str
    robot_name: str


def _render_xacro_to_cached_urdf(mod, description_module: str,
                                 xacro_path: Path) -> Path:
    """
    Rend le Xacro d'un module robot_descriptions en URDF et écrit le
    résultat dans le cache, à côté du Xacro source. Retourne le chemin de
    l'URDF rendu.

    Le nom du fichier rendu inclut le nom du module : deux modules peuvent
    partager le même Xacro avec des XACRO_ARGS différents (ex. UR5e et
    UR10e partagent ur.urdf.xacro) et ne doivent donc pas s'écraser.
    """
    repo_root = Path(mod.REPOSITORY_PATH)
    xacro_args = getattr(mod, "XACRO_ARGS", {})  # {} => rendu par défaut

    urdf_text = render_xacro_to_urdf(
        xacro_path, repo_root, xacro_args=xacro_args
    )

    rendered_path = xacro_path.parent / f".rendered_{description_module}.urdf"
    rendered_path.write_text(urdf_text, encoding="utf-8")
    return rendered_path


def fetch_via_robot_descriptions(description_module: str) -> FetchResult:
    """
    description_module: nom du module tel qu'utilisé par robot_descriptions,
    ex. "g1_description", "go2_description".
    """
    mod = importlib.import_module(f"robot_descriptions.{description_module}")

    urdf_path_raw = getattr(mod, "URDF_PATH", None)
    xacro_path_raw = getattr(mod, "XACRO_PATH", None)
    xacro_path = Path(xacro_path_raw) if xacro_path_raw else None

    if urdf_path_raw:
        # Cas courant : un URDF pré-rendu est disponible directement.
        urdf_path = Path(urdf_path_raw)
    elif xacro_path is not None:
        # Pas d'URDF prêt : on rend le Xacro nous-mêmes (avec XACRO_ARGS).
        urdf_path = _render_xacro_to_cached_urdf(
            mod, description_module, xacro_path
        )
    else:
        raise RuntimeError(
            f"{description_module} n'expose ni URDF_PATH ni XACRO_PATH "
            f"-- impossible d'en tirer un URDF."
        )

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