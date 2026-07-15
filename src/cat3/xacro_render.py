"""
Rendu Xacro -> URDF autonome (sans installation ROS complète).

Les fichiers Xacro utilisent parfois des substitutions $(find <package>)
pour localiser d'autres fichiers du même dépôt (ROS résout normalement ça
via ament_index_python / rospkg). Sans ROS installé, cette substitution
échoue. On la remplace par une résolution locale : on cherche un dossier
nommé <package> dans le dépôt cloné, et on remplace $(find <package>) par
son chemin absolu avant d'appeler l'outil xacro.

Les fichiers .xacro qui ne contiennent en réalité aucune directive xacro
(cas fréquent : un URDF exporté tel quel avec l'extension .xacro, ex.
AgileX Ranger Mini) passent par le même chemin de code et ressortent
inchangés -- pas de branchement séparé nécessaire.
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_FIND_PATTERN = re.compile(r"\$\(find ([\w\-]+)\)")


def _resolve_find_substitutions(text: str, search_root: Path) -> str:
    def repl(match: "re.Match[str]") -> str:
        package_name = match.group(1)
        for candidate in search_root.rglob(package_name):
            if candidate.is_dir():
                return str(candidate)
        # Laissé tel quel : c'est souvent une référence commentée, ou à un
        # package annexe (ex: package de simulation Gazebo) absent du
        # dépôt collecté. Si elle est réellement utilisée par xacro, le
        # rendu échouera plus loin avec une erreur explicite.
        return match.group(0)

    return _FIND_PATTERN.sub(repl, text)


def render_xacro_to_urdf(xacro_path: Path, repo_root: Path) -> str:
    """
    Rend un fichier .xacro (ou un .urdf déguisé en .xacro) en URDF final.
    Travaille sur une copie temporaire du dépôt pour ne jamais modifier le
    cache brut. Retourne le contenu URDF sous forme de texte.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp) / "repo_copy"
        # symlinks=True : certains paquets ROS/catkin contiennent un
        # CMakeLists.txt symlinké vers /opt/ros/.../toplevel.cmake, absent
        # de cet environnement. Copier le lien tel quel évite une erreur
        # de copie sur une cible cassée -- il n'est de toute façon jamais
        # lu par xacro.
        shutil.copytree(repo_root, tmp_root, symlinks=True)

        relative_xacro = xacro_path.relative_to(repo_root)
        tmp_xacro_path = tmp_root / relative_xacro

        for f in tmp_root.rglob("*.xacro"):
            original = f.read_text(errors="ignore")
            patched = _resolve_find_substitutions(original, tmp_root)
            if patched != original:
                f.write_text(patched)

        result = subprocess.run(
            ["xacro", str(tmp_xacro_path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Echec du rendu xacro pour {xacro_path}:\n{result.stderr}"
            )
        return result.stdout
