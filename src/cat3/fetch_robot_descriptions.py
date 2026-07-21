"""
Fetch through the robot_descriptions.py library.

The library handles cloning, local caching of the source repository, and
attaches the declared license (license_spdx) together with the origin
repository (with a pinned commit, for reproducibility).

It does NOT always expose a ready-to-use URDF, however: roughly one module
in six only provides a XACRO_PATH (Franka FER/FR3, UR5e/UR10e, Kinova Gen3,
xArm6/7...). For those we render the Xacro ourselves through
xacro_render.py, forwarding the XACRO_ARGS the library declares (e.g. for
UR: {"ur_type": "ur5e", "name": "ur5e"}; without them xacro fails with
"Undefined substitution argument"). The rendered result is cached next to
the source Xacro so that FetchResult.urdf_path always points at a valid
URDF -- the rest of the pipeline (collect_pilot) therefore never has to
know whether a rendering step took place.
"""

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from robot_descriptions._descriptions import DESCRIPTIONS
from robot_descriptions._repositories import REPOSITORIES

from cat3.xacro_render import render_xacro_to_urdf


@dataclass
class FetchResult:
    urdf_path: Path
    xacro_path: Optional[Path]     # set only when the source is a Xacro
    repo_url: str
    repo_commit: str
    license_spdx: Optional[str]
    maker: str
    robot_name: str


def _render_xacro_to_cached_urdf(mod, description_module: str,
                                 xacro_path: Path) -> Path:
    """
    Render the Xacro of a robot_descriptions module into URDF and write the
    result to the cache, next to the source Xacro. Returns the path of the
    rendered URDF.

    The rendered filename includes the module name: two modules can share
    the same Xacro with different XACRO_ARGS (e.g. UR5e and UR10e both use
    ur.urdf.xacro) and must therefore not overwrite each other.
    """
    repo_root = Path(mod.REPOSITORY_PATH)
    xacro_args = getattr(mod, "XACRO_ARGS", {})  # {} => default rendering

    urdf_text = render_xacro_to_urdf(
        xacro_path, repo_root, xacro_args=xacro_args
    )

    rendered_path = xacro_path.parent / f".rendered_{description_module}.urdf"
    rendered_path.write_text(urdf_text, encoding="utf-8")
    return rendered_path


def fetch_via_robot_descriptions(description_module: str) -> FetchResult:
    """
    description_module: module name as used by robot_descriptions,
    e.g. "g1_description", "go2_description".
    """
    mod = importlib.import_module(f"robot_descriptions.{description_module}")

    urdf_path_raw = getattr(mod, "URDF_PATH", None)
    xacro_path_raw = getattr(mod, "XACRO_PATH", None)
    xacro_path = Path(xacro_path_raw) if xacro_path_raw else None

    if urdf_path_raw:
        # Common case: a pre-rendered URDF is directly available.
        urdf_path = Path(urdf_path_raw)
    elif xacro_path is not None:
        # No ready URDF: render the Xacro ourselves (with XACRO_ARGS).
        urdf_path = _render_xacro_to_cached_urdf(
            mod, description_module, xacro_path
        )
    else:
        raise RuntimeError(
            f"{description_module} exposes neither URDF_PATH nor XACRO_PATH "
            f"-- no URDF can be derived from it."
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
