"""
Standalone Xacro -> URDF rendering (no full ROS installation required).

Xacro files sometimes use $(find <package>) substitutions to locate other
files (ROS resolves these through ament_index_python / rospkg). Without ROS
we resolve them locally: we look for a directory named <package> under a
search root and replace $(find <package>) with its absolute path before
invoking the xacro tool.

Some Xacro files need arguments (xacro_args, e.g. ur_type:=ur5e); others
reference the repository itself as a package (package == repository root);
others still -- not handled here -- reference packages living in separate
third-party repositories (see the note in render_xacro_to_urdf).

A .xacro file containing no xacro directive at all (a URDF disguised as a
.xacro, e.g. Ranger Mini) goes through the same path and comes out
unchanged.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

_FIND_PATTERN = re.compile(r"\$\(find ([\w\-]+)\)")


def _resolve_find_substitutions(text: str, search_root: Path) -> str:
    def repl(match: "re.Match[str]") -> str:
        package_name = match.group(1)
        # Case 1: the package IS the search root itself (common with
        # ur_description, franka_description...). rglob does not descend
        # into itself, so this case is handled explicitly.
        if search_root.name == package_name:
            return str(search_root)
        # Case 2: the package is a subdirectory (possibly of a third-party
        # repository if search_root is the cache root).
        for candidate in search_root.rglob(package_name):
            if candidate.is_dir():
                return str(candidate)
        # Otherwise: left as-is (often a commented-out reference or a
        # missing optional package). If xacro genuinely needs it, the error
        # will surface later, explicitly.
        return match.group(0)

    return _FIND_PATTERN.sub(repl, text)


def render_xacro_to_urdf(
    xacro_path: Path,
    repo_root: Path,
    xacro_args: Optional[dict] = None,
    find_search_root: Optional[Path] = None,
) -> str:
    """
    Render a .xacro (or a .urdf disguised as .xacro) into final URDF.

    - xacro_args: arguments passed to xacro as key:=value pairs
      (e.g. {"ur_type": "ur5e", "name": "ur5e"}). Required by some generic
      Xacro files, otherwise "Undefined substitution argument".
    - find_search_root: root under which $(find pkg) is resolved. Defaults
      to repo_root. Passing the robot_descriptions cache root allows
      resolving packages that live in neighbouring repositories
      (cross-repo dependencies).

    Works on a temporary copy so the cache is never modified. Returns the
    URDF content as text.
    """
    xacro_args = xacro_args or {}
    with tempfile.TemporaryDirectory() as tmp:
        # The repository name is PRESERVED (e.g. "ur_description") so that
        # resolving $(find <repo_name>) works (the package == root case).
        # An earlier version copied to "repo_copy" and broke that case.
        tmp_root = Path(tmp) / repo_root.name
        # symlinks=True: some packages contain a CMakeLists.txt symlinked
        # to /opt/ros/... (target absent here). Copying the link as-is
        # avoids a broken-target error -- xacro never reads it.
        shutil.copytree(repo_root, tmp_root, symlinks=True)

        relative_xacro = xacro_path.relative_to(repo_root)
        tmp_xacro_path = tmp_root / relative_xacro

        search_root = tmp_root if find_search_root is None else find_search_root
        for f in tmp_root.rglob("*.xacro"):
            original = f.read_text(errors="ignore")
            patched = _resolve_find_substitutions(original, search_root)
            if patched != original:
                f.write_text(patched)

        cmd = ["xacro", str(tmp_xacro_path)]
        cmd += [f"{k}:={v}" for k, v in xacro_args.items()]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"xacro rendering failed for {xacro_path}:\n{result.stderr}"
            )
        return result.stdout
