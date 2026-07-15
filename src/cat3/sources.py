"""
Catalogue déclaratif des robots à collecter pour la catégorie 3
(URDF & Robot Specs).

Ajouter un robot au pilote = ajouter une entrée ici. Aucun autre fichier
n'a besoin d'être modifié pour scaler à un nouveau robot -- c'est le seul
endroit du pipeline qui connaît des noms de robots en dur.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class SourceType(Enum):
    # Récupération via la bibliothèque robot_descriptions.py : elle gère
    # elle-même le clone, le cache, le rendu Xacro -> URDF si besoin, et
    # expose la licence déclarée du dépôt source.
    ROBOT_DESCRIPTIONS = "robot_descriptions"

    # Récupération directe depuis un dépôt git (utilisé quand le robot
    # n'est pas dans le catalogue de robot_descriptions.py).
    GIT_REPO = "git_repo"


@dataclass
class RobotSource:
    robot_id: str            # identifiant interne stable, ex: "unitree_g1"
    display_name: str        # nom lisible, ex: "Unitree G1"
    source_type: SourceType
    fleet_priority: bool = False   # fait partie de la flotte prioritaire
    notes: str = ""

    # --- champs utilisés si source_type == ROBOT_DESCRIPTIONS ---
    description_module: Optional[str] = None   # ex: "g1_description"

    # --- champs utilisés si source_type == GIT_REPO ---
    repo_url: Optional[str] = None
    repo_ref: Optional[str] = None                # branche à cloner
    file_path_in_repo: Optional[str] = None       # chemin du .urdf/.xacro
    known_license_spdx: Optional[str] = None      # None si pas de licence trouvée


PILOT_CATALOG: List[RobotSource] = [
    RobotSource(
        robot_id="unitree_g1",
        display_name="Unitree G1",
        source_type=SourceType.ROBOT_DESCRIPTIONS,
        description_module="g1_description",
        fleet_priority=True,
    ),
    RobotSource(
        robot_id="unitree_go2",
        display_name="Unitree Go2",
        source_type=SourceType.ROBOT_DESCRIPTIONS,
        description_module="go2_description",
        fleet_priority=True,
    ),
    RobotSource(
        robot_id="agilex_ranger_mini_v3",
        display_name="AgileX Ranger Mini 3.0",
        source_type=SourceType.GIT_REPO,
        repo_url="https://github.com/agilexrobotics/ugv_gazebo_sim.git",
        repo_ref="master",
        file_path_in_repo="ranger_mini/ranger_mini_v3/urdf/ranger_mini.xacro",
        known_license_spdx=None,  # vérifié via l'API GitHub le 2026-07-15 :
                                   # aucun fichier LICENSE dans le dépôt.
        fleet_priority=True,
        notes=(
            "Pas de licence declaree dans le depot source (verifie via "
            "l'API GitHub). Collecte quand meme avec license_status="
            "'no-license', sur decision explicite du projet, a traiter "
            "ulterieurement (cf. echange du 2026-07-15)."
        ),
    ),
]
