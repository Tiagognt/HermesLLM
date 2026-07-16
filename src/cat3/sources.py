"""
Catalogue déclaratif des robots à collecter pour la catégorie 3
(URDF & Robot Specs).

Ajouter un robot au pilote = ajouter une entrée ici. Aucun autre fichier
n'a besoin d'être modifié pour scaler à un nouveau robot -- c'est le seul
endroit du pipeline qui connaît des noms de robots en dur.

Les entrées SourceType.ROBOT_DESCRIPTIONS n'ont pas de licence codée en
dur ici : elle est lue dynamiquement depuis robot_descriptions.py au
moment de la collecte (fetch_robot_descriptions.py), pour rester
synchronisée avec la source de vérité. known_license_spdx n'est utilisé
que pour les entrées GIT_REPO, où il n'existe pas d'équivalent
automatique -- vérifié manuellement par nos soins (inspection réelle du
fichier LICENSE du dépôt).

robot_class reprend la taxonomie utilisée par robot_descriptions.py
(arm, quadruped, humanoid, biped, wheeled, mobile_manipulator, drone,
dual_arm, end_effector) pour préparer le tag "embodiment" attendu à
l'étape de transformation (allocation embodiment-aware).

--------------------------------------------------------------------------
Composition (rééquilibrage "robots complets uniquement") :
  - effecteurs terminaux (grippers/mains) exclus ;
  - un seul bras double conservé (Baxter) ;
  - catégories bipède / mobile / humanoïde renforcées ;
  - 4 sources hors robot_descriptions.py (git direct), licence de chacune
    vérifiée par lecture directe du fichier LICENSE du dépôt.

Toutes les licences (RD + git) ont été classées conformes à l'allowlist
des consignes (MIT / BSD-x-Clause / Apache-2.0 / CC-BY-x.x). Seule
exception assumée : AgileX Ranger Mini (aucune licence -> "no-license",
collecté sur décision explicite du projet).
--------------------------------------------------------------------------
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
    robot_class: str = ""    # arm / quadruped / humanoid / biped / wheeled /
                              # mobile_manipulator / drone / dual_arm / end_effector
    fleet_priority: bool = False   # fait partie de la flotte prioritaire
    notes: str = ""

    # --- champs utilisés si source_type == ROBOT_DESCRIPTIONS ---
    description_module: Optional[str] = None   # ex: "g1_description"

    # --- champs utilisés si source_type == GIT_REPO ---
    repo_url: Optional[str] = None
    repo_ref: Optional[str] = None                # branche à cloner
    file_path_in_repo: Optional[str] = None       # chemin du .urdf/.xacro
    known_license_spdx: Optional[str] = None      # None si pas de licence trouvée


def _rd(robot_id, display_name, description_module, robot_class, fleet_priority=False, notes=""):
    """Raccourci pour une entrée ROBOT_DESCRIPTIONS (le cas le plus fréquent)."""
    return RobotSource(
        robot_id=robot_id,
        display_name=display_name,
        source_type=SourceType.ROBOT_DESCRIPTIONS,
        description_module=description_module,
        robot_class=robot_class,
        fleet_priority=fleet_priority,
        notes=notes,
    )


def _git(robot_id, display_name, robot_class, repo_url, repo_ref, file_path_in_repo,
         known_license_spdx, fleet_priority=False, notes=""):
    """Raccourci pour une entrée GIT_REPO (source hors robot_descriptions.py)."""
    return RobotSource(
        robot_id=robot_id,
        display_name=display_name,
        source_type=SourceType.GIT_REPO,
        robot_class=robot_class,
        repo_url=repo_url,
        repo_ref=repo_ref,
        file_path_in_repo=file_path_in_repo,
        known_license_spdx=known_license_spdx,
        fleet_priority=fleet_priority,
        notes=notes,
    )


PILOT_CATALOG: List[RobotSource] = [

    # ============ QUADRUPÈDES (10) ============
    _rd("unitree_a1", "Unitree A1", "a1_description", "quadruped"),
    _rd("unitree_aliengo", "Unitree Aliengo", "aliengo_description", "quadruped"),
    _rd("anymal_b", "ANYmal B", "anymal_b_description", "quadruped"),
    _rd("anymal_c", "ANYmal C", "anymal_c_description", "quadruped"),
    _rd("anymal_d", "ANYmal D", "anymal_d_description", "quadruped"),
    _rd("unitree_b1", "Unitree B1", "b1_description", "quadruped"),
    _rd("unitree_b2", "Unitree B2", "b2_description", "quadruped"),
    _rd("unitree_go1", "Unitree Go1", "go1_description", "quadruped"),
    _rd("unitree_go2", "Unitree Go2", "go2_description", "quadruped", fleet_priority=True),
    _rd("solo", "Solo", "solo_description", "quadruped"),

    # ============ HUMANOÏDES (12) ============
    _rd("unitree_g1", "Unitree G1", "g1_description", "humanoid", fleet_priority=True),
    _rd("unitree_h1", "Unitree H1", "h1_description", "humanoid"),
    _rd("unitree_h1_2", "Unitree H1_2", "h1_2_description", "humanoid"),
    _rd("atlas_v4", "Atlas v4", "atlas_v4_description", "humanoid"),
    _rd("atlas_drc", "Atlas DRC (v3)", "atlas_drc_description", "humanoid"),
    _rd("booster_t1", "Booster T1", "booster_t1_description", "humanoid"),
    _rd("ergocub", "ergoCub", "ergocub_description", "humanoid"),
    _rd("toddlerbot", "ToddlerBot", "toddlerbot_description", "humanoid"),
    _rd("draco3", "Draco3 (Apptronik)", "draco3_description", "humanoid"),
    _rd("berkeley_humanoid", "Berkeley Humanoid", "berkeley_humanoid_description", "humanoid"),
    _rd("jvrc1", "JVRC-1 (AIST)", "jvrc_description", "humanoid"),
    # -- hors robot_descriptions.py : LICENSE lu directement -> BSD-3-Clause
    _git("robotera_star1", "RobotEra STAR1", "humanoid",
         repo_url="https://github.com/roboterax/models.git",
         repo_ref="main",
         file_path_in_repo="star1/urdf/l3_with_hand_fixedpin_xml.urdf",
         known_license_spdx="BSD-3-Clause",
         notes="URDF direct (pas de Xacro). LICENSE BSD-3-Clause vérifié par "
               "lecture du fichier au root du dépôt."),

    # ============ BIPÈDES (5) ============
    _rd("cassie", "Cassie", "cassie_description", "biped"),
    _rd("bolt", "Bolt", "bolt_description", "biped"),
    _rd("upkie", "Upkie", "upkie_description", "biped"),
    _rd("rhea", "Rhea", "rhea_description", "biped"),
    # -- hors robot_descriptions.py : LICENSE lu directement -> Apache-2.0
    _git("robotis_op3", "ROBOTIS OP3", "biped",
         repo_url="https://github.com/ROBOTIS-GIT/ROBOTIS-OP3-Common.git",
         repo_ref="master",
         file_path_in_repo="op3_description/urdf/robotis_op3.urdf.xacro",
         known_license_spdx="Apache-2.0",
         notes="Xacro auto-contenu (aucune dépendance externe). LICENSE "
               "Apache-2.0 vérifié par lecture du fichier au root du dépôt."),

    # ============ MOBILE À ROUES (1 + Ranger Mini ci-dessous) ============
    _rd("rsk_omnidirectional", "RSK Omnidirectional", "rsk_description", "wheeled"),

    # ============ BRAS MANIPULATEURS (12) ============
    _rd("franka_fer", "Franka FER", "fer_description", "arm"),
    _rd("franka_fr3", "Franka FR3", "fr3_description", "arm"),
    _rd("franka_panda", "Franka Panda", "panda_description", "arm"),
    _rd("kuka_iiwa14", "KUKA iiwa 14", "iiwa14_description", "arm"),
    _rd("kuka_iiwa7", "KUKA iiwa 7", "iiwa7_description", "arm"),
    _rd("ur5e", "Universal Robots UR5e", "ur5e_description", "arm"),
    _rd("ur10e", "Universal Robots UR10e", "ur10e_description", "arm"),
    _rd("kinova_gen3", "Kinova Gen3", "gen3_description", "arm"),
    _rd("xarm6", "UFACTORY xArm6", "xarm6_description", "arm"),
    _rd("xarm7", "UFACTORY xArm7", "xarm7_description", "arm"),
    _rd("agilex_piper", "AgileX PiPER", "piper_description", "arm"),
    _rd("unitree_z1", "Unitree Z1", "z1_description", "arm"),

    # ============ MANIPULATEURS MOBILES (7) ============
    _rd("fetch", "Fetch", "fetch_description", "mobile_manipulator"),
    _rd("tiago", "TIAGo (official)", "tiago_official_description", "mobile_manipulator"),
    _rd("reachy", "Reachy", "reachy_description", "mobile_manipulator"),
    _rd("pepper", "Pepper", "pepper_description", "mobile_manipulator"),
    _rd("rby1", "RBY1", "rby1_description", "mobile_manipulator"),
    _rd("eve_r3", "Eve R3", "eve_r3_description", "mobile_manipulator"),
    _rd("bambot", "BamBot", "bambot_description", "mobile_manipulator"),

    # ============ DRONES (3) ============
    _rd("crazyflie2", "Crazyflie 2.0", "cf2_description", "drone"),
    _rd("skydio_x2", "Skydio X2", "skydio_x2_description", "drone"),
    # -- hors robot_descriptions.py : LICENSE lu directement -> Apache-2.0
    _git("nasa_ingenuity", "NASA JPL Ingenuity", "drone",
         repo_url="https://github.com/david-dorf/perseverance-ingenuity-urdfs.git",
         repo_ref="main",
         file_path_in_repo="ingenuity/ingenuity.urdf",
         known_license_spdx="Apache-2.0",
         notes="URDF direct (pas de Xacro). LICENSE Apache-2.0 vérifié par "
               "lecture du fichier au root du dépôt."),

    # ============ BRAS DOUBLE (1) ============
    _rd("baxter", "Baxter", "baxter_description", "dual_arm"),

    # ============ VÉHICULE TERRESTRE À ROUES -- hors robot_descriptions.py ============
    RobotSource(
        robot_id="agilex_ranger_mini_v3",
        display_name="AgileX Ranger Mini 3.0",
        source_type=SourceType.GIT_REPO,
        robot_class="wheeled",
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

# NB : le set des robots dont l'absence de licence est tolérée
# (ALLOW_NO_LICENSE_FOR = {"agilex_ranger_mini_v3"}) vit actuellement dans
# collect_pilot.py. Aucun des robots git ajoutés ici n'a besoin d'y figurer :
# ils ont tous une licence conforme vérifiée. Ne pas dupliquer ce set ici
# pour éviter qu'il diverge de celui de collect_pilot.py.