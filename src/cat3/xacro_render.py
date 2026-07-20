"""
Rendu Xacro -> URDF autonome (sans installation ROS complète).

Les fichiers Xacro utilisent parfois des substitutions $(find <package>)
pour localiser d'autres fichiers (ROS résout ça via ament_index_python /
rospkg). Sans ROS, on résout localement : on cherche un dossier nommé
<package> sous une racine de recherche, et on remplace $(find <package>)
par son chemin absolu avant d'appeler l'outil xacro.

Certains Xacro ont besoin d'arguments (xacro_args, ex. ur_type:=ur5e) ;
d'autres référencent le dépôt lui-même comme paquet (package == racine du
dépôt) ; d'autres encore, non gérés ici, référencent des paquets situés
dans des dépôts tiers séparés (voir note dans render_xacro_to_urdf).

Les .xacro qui ne contiennent aucune directive xacro (URDF déguisé en
.xacro, ex. Ranger Mini) passent par le même chemin et ressortent
inchangés.
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
        # Cas 1 : le paquet EST la racine de recherche elle-même
        # (fréquent : ur_description, franka_description...). rglob ne
        # descend pas sur soi-même, on le traite explicitement.
        if search_root.name == package_name:
            return str(search_root)
        # Cas 2 : le paquet est un sous-dossier (éventuellement d'un dépôt
        # tiers si search_root est la racine du cache).
        for candidate in search_root.rglob(package_name):
            if candidate.is_dir():
                return str(candidate)
        # Sinon : laissé tel quel (souvent une référence commentée ou un
        # paquet annexe absent). Si xacro en a réellement besoin, l'erreur
        # surviendra plus loin, explicite.
        return match.group(0)

    return _FIND_PATTERN.sub(repl, text)


def render_xacro_to_urdf(
    xacro_path: Path,
    repo_root: Path,
    xacro_args: Optional[dict] = None,
    find_search_root: Optional[Path] = None,
) -> str:
    """
    Rend un .xacro (ou un .urdf déguisé en .xacro) en URDF final.

    - xacro_args : arguments passés à xacro sous forme key:=value
      (ex. {"ur_type": "ur5e", "name": "ur5e"}). Requis par certains Xacro
      génériques, sinon "Undefined substitution argument".
    - find_search_root : racine sous laquelle résoudre les $(find pkg).
      Par défaut = repo_root. Passer la racine du cache robot_descriptions
      permet de résoudre des paquets situés dans des dépôts voisins
      (dépendances cross-repo).

    Travaille sur une copie temporaire pour ne jamais modifier le cache.
    Retourne le contenu URDF sous forme de texte.
    """
    xacro_args = xacro_args or {}
    with tempfile.TemporaryDirectory() as tmp:
        # On PRÉSERVE le nom du dépôt (ex: "ur_description") pour que la
        # résolution de $(find <nom_du_dépôt>) fonctionne (cas paquet ==
        # racine). L'ancien code copiait vers "repo_copy" et cassait ce cas.
        tmp_root = Path(tmp) / repo_root.name
        # symlinks=True : certains paquets contiennent un CMakeLists.txt
        # symlinké vers /opt/ros/... (cible absente ici). Copier le lien
        # tel quel évite une erreur sur cible cassée -- xacro ne le lit pas.
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
                f"Echec du rendu xacro pour {xacro_path}:\n{result.stderr}"
            )
        return result.stdout