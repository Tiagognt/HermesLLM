"""
Catalogue déclaratif des sources de la catégorie 1 (General Robot Data,
tier A).

Ajouter une source = ajouter une entrée ici. C'est le SEUL fichier de cat1
qui contienne des noms de dépôts en dur, comme `cat3/sources.py` pour les
robots.

--------------------------------------------------------------------------
LICENCES
Chaque `license_spdx` ci-dessous a été vérifié à la main le 2026-07-21, en
lisant le fichier LICENSE du dépôt (l'API GitHub renvoyait `NOASSERTION`
pour plusieurs d'entre eux, dont navigation2, PythonRobotics, OMPL et
PX4-user_guide, tous conformes en réalité). `collect_docs.py` relit ce
fichier au moment de la collecte et SIGNALE tout désaccord avec la valeur
déclarée ici -- le catalogue fait foi, mais un écart n'est jamais tu.

Écartés après vérification, et pourquoi :
  ros-infrastructure/rep          aucun LICENSE      -> no-license
  ros/ros_tutorials               aucun LICENSE      -> no-license
  ros-simulation/gazebo_ros_pkgs  aucun LICENSE      -> no-license
  OpenGVLab/Instruct2Act          aucun LICENSE      -> no-license
  NVlabs/progprompt-vh            NVIDIA License     -> hors allowlist
  SteveMacenski/slam_toolbox      LGPL-2.1           -> hors allowlist
  bulletphysics/bullet3           zlib               -> hors allowlist
Deux des trois sources « planning-as-code » nommées par les consignes
(ProgPrompt, Instruct2Act) sont donc inutilisables : seule Code-as-Policies
subsiste.

--------------------------------------------------------------------------
QUOTAS
`token_budget` est un PLAFOND appliqué en phase 2, après déduplication.
Il existe parce que le volume disponible dépasse largement la cible : la
seule documentation ROS 2 pèse ~1,18 M tokens, soit à elle seule la
majorité de cat1. Sans plafond, le corpus prendrait le style d'une source
unique. Les budgets sont donc un outil de DIVERSITÉ, pas de volume.

Ajuster la taille finale de cat1 = modifier ces nombres et relancer la
phase 2. Aucune recollecte n'est nécessaire.
--------------------------------------------------------------------------
"""

from dataclasses import dataclass, field
from typing import List, Optional

# Natures de contenu (= niveau <kind> de data/cat1/raw/<kind>/<source_id>/)
KIND_DOCS = "docs"
KIND_INTERFACES = "interfaces"
KIND_CODE = "code"
KIND_NOTEBOOKS = "notebooks"


@dataclass
class RepoSource:
    source_id: str               # identifiant interne stable
    display_name: str
    family: str                  # regroupement pour les stats et la diversité
    kind: str                    # KIND_*
    repo_url: str
    repo_ref: str
    license_spdx: str            # vérifié à la main (voir en-tête)
    include_globs: List[str]
    token_budget: int
    exclude_globs: List[str] = field(default_factory=list)
    sparse_paths: Optional[List[str]] = None
    url: str = ""                # page humaine, pour le champ `url` du corpus
    notes: str = ""


# Exclusions communes à tous les dépôts : bruit d'outillage, pas du contenu.
COMMON_EXCLUDES = [
    ".github/*", "*/.github/*", "_static/*", "*/_static/*",
    "CHANGELOG*", "*/CHANGELOG*", "CONTRIBUTING*", "CODE_OF_CONDUCT*",
]


CATALOG: List[RepoSource] = [

    # ======================================================================
    # FAMILLE « ros_docs » -- le socle de connaissance ROS.
    # Plafonné volontairement : ces dépôts pourraient à eux seuls remplir
    # tout cat1 et noyer le reste du corpus.
    # ======================================================================
    RepoSource(
        source_id="ros2_documentation", display_name="ROS 2 Documentation",
        family="ros_docs", kind=KIND_DOCS,
        repo_url="https://github.com/ros2/ros2_documentation.git",
        repo_ref="rolling", license_spdx="CC-BY-4.0",
        include_globs=["source/**/*.rst"],
        exclude_globs=COMMON_EXCLUDES + ["source/Releases/*"],
        token_budget=300_000,
        url="https://docs.ros.org/en/rolling/",
        notes="~1,18 M tokens disponibles, plafonné à 300 k pour la diversité. "
              "Les notes de version (Releases/) sont exclues : très répétitives "
              "d'une distribution à l'autre.",
    ),
    RepoSource(
        source_id="nav2_docs", display_name="Nav2 Documentation",
        family="ros_docs", kind=KIND_DOCS,
        repo_url="https://github.com/ros-navigation/docs.nav2.org.git",
        repo_ref="master", license_spdx="Apache-2.0",
        include_globs=["**/*.rst", "**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=140_000,
        url="https://docs.nav2.org/",
        notes="Navigation autonome : configuration, arbres de comportement, "
              "greffons. Directement utile à la planification par robot.",
    ),
    RepoSource(
        source_id="moveit2_tutorials", display_name="MoveIt 2 Tutorials",
        family="ros_docs", kind=KIND_DOCS,
        repo_url="https://github.com/moveit/moveit2_tutorials.git",
        repo_ref="main", license_spdx="BSD-3-Clause",
        include_globs=["doc/**/*.rst", "doc/**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=90_000,
        url="https://moveit.picknik.ai/",
        notes="Manipulation : planification de mouvement, cinématique, saisie.",
    ),
    RepoSource(
        source_id="ros2_design", display_name="ROS 2 Design Articles",
        family="ros_docs", kind=KIND_DOCS,
        repo_url="https://github.com/ros2/design.git",
        repo_ref="gh-pages", license_spdx="Apache-2.0",
        include_globs=["articles/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=90_000,
        url="https://design.ros2.org/",
        notes="Prose de RATIONALE (pourquoi telle abstraction existe), pas des "
              "tutoriels. Densité conceptuelle élevée, style différent du reste.",
    ),
    RepoSource(
        source_id="ros2_control_docs", display_name="ros2_control Documentation",
        family="ros_docs", kind=KIND_DOCS,
        repo_url="https://github.com/ros-controls/control.ros.org.git",
        repo_ref="rolling", license_spdx="Apache-2.0",
        include_globs=["**/*.rst", "**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=40_000,
        url="https://control.ros.org/",
        notes="Couche de commande matérielle : le lien entre planification "
              "et actionneurs.",
    ),

    # ======================================================================
    # FAMILLE « sim_docs » -- documentation des simulateurs.
    # Priorité relevée à la demande de l'utilisateur : l'entraînement
    # comportera du sim-to-real, donc savoir décrire et piloter un
    # simulateur fait partie de la connaissance utile.
    # ======================================================================
    RepoSource(
        source_id="gazebo_docs", display_name="Gazebo Documentation",
        family="sim_docs", kind=KIND_DOCS,
        repo_url="https://github.com/gazebosim/docs.git",
        repo_ref="master", license_spdx="CC-BY-4.0",
        # Le dépôt publie 12 versions en parallèle (citadel, fortress,
        # garden, harmonic, ionic, jetty...) dont ~85 % de contenu commun.
        # On ne prend QUE la LTS harmonic + le tronc commun ; laisser les
        # autres reviendrait à faire porter tout le travail au dédoublonneur.
        include_globs=["harmonic/**/*.md", "common/**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=120_000,
        url="https://gazebosim.org/docs",
    ),
    RepoSource(
        source_id="mujoco_docs", display_name="MuJoCo Documentation",
        family="sim_docs", kind=KIND_DOCS,
        repo_url="https://github.com/google-deepmind/mujoco.git",
        repo_ref="main", license_spdx="Apache-2.0",
        include_globs=["doc/**/*.rst", "doc/**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=90_000,
        url="https://mujoco.readthedocs.io/",
        notes="Modélisation physique : contacts, actionneurs, capteurs. "
              "Complémentaire des URDF de cat3.",
    ),
    RepoSource(
        source_id="webots_docs", display_name="Webots Documentation",
        family="sim_docs", kind=KIND_DOCS,
        repo_url="https://github.com/cyberbotics/webots.git",
        repo_ref="master", license_spdx="Apache-2.0",
        include_globs=["docs/guide/**/*.md", "docs/reference/**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=80_000,
        url="https://cyberbotics.com/doc/guide/index",
    ),
    RepoSource(
        source_id="drake_docs", display_name="Drake Documentation",
        family="sim_docs", kind=KIND_DOCS,
        repo_url="https://github.com/RobotLocomotion/drake.git",
        repo_ref="master", license_spdx="BSD-3-Clause",
        include_globs=["doc/**/*.rst", "doc/**/*.md", "tutorials/**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=60_000,
        url="https://drake.mit.edu/",
        notes="Dynamique multicorps et optimisation — le versant « contrôle » "
              "que la doc ROS couvre peu.",
    ),

    # ======================================================================
    # FAMILLE « interfaces » -- .msg / .srv / .action.
    # Le poste le plus directement utile à l'étape (4) « action-function
    # selection » : c'est littéralement le vocabulaire de commande que le
    # modèle devra produire. Faible volume, densité maximale.
    # ======================================================================
    RepoSource(
        source_id="common_interfaces", display_name="ROS 2 Common Interfaces",
        family="interfaces", kind=KIND_INTERFACES,
        repo_url="https://github.com/ros2/common_interfaces.git",
        repo_ref="rolling", license_spdx="Apache-2.0",
        include_globs=["**/msg/*.msg", "**/srv/*.srv", "**/action/*.action"],
        token_budget=40_000,
        url="https://github.com/ros2/common_interfaces",
        notes="geometry_msgs/Twist, sensor_msgs/*, nav_msgs/* ... "
              "Licence portée par chaque paquet (pas de LICENSE racine).",
    ),
    RepoSource(
        source_id="nav2_msgs", display_name="Nav2 Interfaces",
        family="interfaces", kind=KIND_INTERFACES,
        repo_url="https://github.com/ros-navigation/navigation2.git",
        repo_ref="main", license_spdx="Apache-2.0",
        include_globs=["**/msg/*.msg", "**/srv/*.srv", "**/action/*.action"],
        token_budget=25_000,
        url="https://github.com/ros-navigation/navigation2",
        notes="NavigateToPose, ComputePathToPose, FollowWaypoints : les "
              "actions de navigation de haut niveau. LICENSE du dépôt = "
              "« Apache-2.0 AND BSD-3-Clause », défaut Apache-2.0.",
    ),
    RepoSource(
        source_id="control_msgs", display_name="control_msgs",
        family="interfaces", kind=KIND_INTERFACES,
        repo_url="https://github.com/ros-controls/control_msgs.git",
        repo_ref="master", license_spdx="BSD-3-Clause",
        include_globs=["**/msg/*.msg", "**/srv/*.srv", "**/action/*.action"],
        token_budget=20_000,
        url="https://github.com/ros-controls/control_msgs",
        notes="FollowJointTrajectory, GripperCommand : la commande articulaire.",
    ),
    RepoSource(
        source_id="moveit_msgs", display_name="moveit_msgs",
        family="interfaces", kind=KIND_INTERFACES,
        repo_url="https://github.com/moveit/moveit_msgs.git",
        repo_ref="ros2", license_spdx="BSD-3-Clause",
        include_globs=["**/msg/*.msg", "**/srv/*.srv", "**/action/*.action"],
        token_budget=25_000,
        url="https://github.com/moveit/moveit_msgs",
        notes="MoveGroup, Grasp, CollisionObject : la manipulation planifiée.",
    ),

    # ======================================================================
    # FAMILLE « algorithms » -- algorithmie robotique commentée.
    # ======================================================================
    RepoSource(
        source_id="python_robotics", display_name="PythonRobotics",
        family="algorithms", kind=KIND_CODE,
        repo_url="https://github.com/AtsushiSakai/PythonRobotics.git",
        repo_ref="master", license_spdx="MIT",
        include_globs=["**/*.py", "docs/**/*.rst", "*.md"],
        exclude_globs=COMMON_EXCLUDES + ["tests/*"],
        token_budget=80_000,
        url="https://atsushisakai.github.io/PythonRobotics/",
        notes="Planification de trajectoire, SLAM, localisation, contrôle — "
              "chaque algorithme est écrit pour être lu.",
    ),
    RepoSource(
        source_id="modern_robotics", display_name="Modern Robotics (Lynch & Park)",
        family="algorithms", kind=KIND_CODE,
        repo_url="https://github.com/NxRLab/ModernRobotics.git",
        repo_ref="master", license_spdx="MIT",
        include_globs=["packages/Python/**/*.py", "*.md", "**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=35_000,
        url="https://github.com/NxRLab/ModernRobotics",
        notes="Bibliothèque du manuel de référence : cinématique, dynamique, "
              "génération de trajectoire, avec docstrings pédagogiques.",
    ),
    RepoSource(
        source_id="robotics_toolbox", display_name="Robotics Toolbox for Python",
        family="algorithms", kind=KIND_CODE,
        repo_url="https://github.com/petercorke/robotics-toolbox-python.git",
        repo_ref="master", license_spdx="MIT",
        include_globs=["roboticstoolbox/**/*.py", "docs/source/**/*.rst", "*.md"],
        exclude_globs=COMMON_EXCLUDES + ["tests/*", "roboticstoolbox/data/*"],
        token_budget=50_000,
        url="https://petercorke.github.io/robotics-toolbox-python/",
    ),
    RepoSource(
        source_id="ompl", display_name="OMPL",
        family="algorithms", kind=KIND_CODE,
        repo_url="https://github.com/ompl/ompl.git",
        repo_ref="main", license_spdx="BSD-3-Clause",
        include_globs=["doc/markdown/*.md", "demos/**/*.py", "demos/**/*.cpp"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=45_000,
        url="https://ompl.kavrakilab.org/",
        notes="Planification de mouvement par échantillonnage : RRT, PRM... "
              "Le socle algorithmique sous MoveIt.",
    ),
    RepoSource(
        source_id="pinocchio", display_name="Pinocchio",
        family="algorithms", kind=KIND_CODE,
        repo_url="https://github.com/stack-of-tasks/pinocchio.git",
        repo_ref="devel", license_spdx="BSD-2-Clause",
        include_globs=["examples/**/*.py", "doc/**/*.md", "*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=35_000,
        url="https://stack-of-tasks.github.io/pinocchio/",
        notes="Dynamique des corps articulés — exploite directement les URDF "
              "collectés en cat3.",
    ),

    # ======================================================================
    # FAMILLE « examples » -- code écrit pour être lu (nœuds, patterns).
    # ======================================================================
    RepoSource(
        source_id="ros2_examples", display_name="ROS 2 Examples",
        family="examples", kind=KIND_CODE,
        repo_url="https://github.com/ros2/examples.git",
        repo_ref="rolling", license_spdx="Apache-2.0",
        include_globs=["**/*.py", "**/*.cpp", "**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=50_000,
        url="https://github.com/ros2/examples",
        notes="Patterns canoniques : publisher/subscriber, service, action, "
              "paramètres. C'est la forme que doit prendre un « nœud ROS ».",
    ),
    RepoSource(
        source_id="ros2_demos", display_name="ROS 2 Demos",
        family="examples", kind=KIND_CODE,
        repo_url="https://github.com/ros2/demos.git",
        repo_ref="rolling", license_spdx="Apache-2.0",
        include_globs=["**/*.py", "**/*.cpp", "**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=60_000,
        url="https://github.com/ros2/demos",
    ),
    RepoSource(
        source_id="moveit_task_constructor", display_name="MoveIt Task Constructor",
        family="examples", kind=KIND_CODE,
        repo_url="https://github.com/ros-planning/moveit_task_constructor.git",
        repo_ref="master", license_spdx="BSD-3-Clause",
        include_globs=["**/*.md", "demo/**/*.py", "demo/**/*.cpp", "core/doc/*"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=40_000,
        url="https://github.com/ros-planning/moveit_task_constructor",
        notes="DÉCOMPOSITION d'une tâche de manipulation en étapes — le plus "
              "proche, côté manipulation, de ce que cat2 apportera pour "
              "l'allocation multi-robots.",
    ),
    # -- ajouts 2026-07-21 : les arbres de comportement sont le modèle
    #    d'EXÉCUTION de la planification par robot (Nav2 s'en sert pour son
    #    BT Navigator). Aucune source ne les couvrait, alors que c'est
    #    exactement l'étape (3) « per-robot task planning » de la cible.
    RepoSource(
        source_id="behaviortree_cpp", display_name="BehaviorTree.CPP",
        family="examples", kind=KIND_CODE,
        repo_url="https://github.com/BehaviorTree/BehaviorTree.CPP.git",
        repo_ref="master", license_spdx="MIT",
        include_globs=["examples/**/*.cpp", "sample_nodes/**/*.cpp",
                       "sample_nodes/**/*.h", "README.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=35_000,
        url="https://www.behaviortree.dev/",
        notes="Bibliothèque d'arbres de comportement utilisée par le BT "
              "Navigator de Nav2. La documentation prose vit sur un site "
              "séparé (pas de dépôt source public) : on prend les exemples, "
              "qui sont écrits pour être lus.",
    ),
    RepoSource(
        source_id="py_trees", display_name="py_trees",
        family="examples", kind=KIND_CODE,
        repo_url="https://github.com/splintered-reality/py_trees.git",
        repo_ref="devel", license_spdx="BSD-3-Clause",
        include_globs=["docs/*.rst", "py_trees/**/*.py", "README.md"],
        exclude_globs=COMMON_EXCLUDES + ["tests/*"],
        token_budget=45_000,
        url="https://py-trees.readthedocs.io/",
        notes="Versant prose des arbres de comportement : terminologie, "
              "idiomes, composites, décorateurs. Complète BehaviorTree.CPP, "
              "qui n'apporte que du code.",
    ),
    RepoSource(
        source_id="px4_user_guide", display_name="PX4 Autopilot User Guide",
        family="sim_docs", kind=KIND_DOCS,
        repo_url="https://github.com/PX4/PX4-user_guide.git",
        repo_ref="main", license_spdx="CC-BY-4.0",
        include_globs=["en/**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=70_000,
        url="https://docs.px4.io/",
        notes="Volet DRONE, absent de cat1 alors que la flotte cible en "
              "comporte un. Modes de vol, missions, sécurité, simulation SITL "
              "— le pendant aérien de ce que Nav2 apporte au sol.",
    ),
    RepoSource(
        source_id="ros2_controllers", display_name="ros2_controllers",
        family="examples", kind=KIND_CODE,
        repo_url="https://github.com/ros-controls/ros2_controllers.git",
        repo_ref="master", license_spdx="Apache-2.0",
        include_globs=["**/doc/*.rst", "**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=40_000,
        url="https://control.ros.org/",
    ),

    # ======================================================================
    # FAMILLE « planning_code » -- langage naturel -> code de planification.
    # Demandée explicitement par les consignes, mais très réduite en
    # pratique : voir les exclusions en en-tête.
    # ======================================================================
    RepoSource(
        source_id="code_as_policies", display_name="Code as Policies",
        family="planning_code", kind=KIND_NOTEBOOKS,
        repo_url="https://github.com/google-research/google-research.git",
        repo_ref="master", license_spdx="Apache-2.0",
        include_globs=["code_as_policies/**/*.ipynb", "code_as_policies/**/*.md"],
        # Dépôt monolithique de plusieurs Go : sparse checkout obligatoire.
        # On matérialise aussi /LICENSE, sinon la contre-vérification de
        # licence ne trouve rien et signale un faux problème.
        sparse_paths=["code_as_policies", "LICENSE"],
        token_budget=30_000,
        url="https://code-as-policies.github.io/",
        notes="Seule des trois sources planning-as-code des consignes à être "
              "sous licence conforme (ProgPrompt = NVIDIA License, "
              "Instruct2Act = aucune licence).",
    ),
    RepoSource(
        source_id="unified_planning", display_name="AIPlan4EU Unified Planning",
        family="planning_code", kind=KIND_CODE,
        repo_url="https://github.com/aiplan4eu/unified-planning.git",
        repo_ref="master", license_spdx="Apache-2.0",
        include_globs=["docs/**/*.rst", "docs/**/*.md", "*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=50_000,
        url="https://unified-planning.readthedocs.io/",
        notes="Représentation formelle de problèmes de planification (PDDL, "
              "actions, préconditions, effets) : le pont entre langage "
              "naturel et plan exécutable.",
    ),
    RepoSource(
        source_id="virtualhome", display_name="VirtualHome",
        family="planning_code", kind=KIND_CODE,
        repo_url="https://github.com/xavierpuigf/virtualhome.git",
        repo_ref="master", license_spdx="MIT",
        include_globs=["**/*.md", "demo/**/*.py", "simulation/**/*.py"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=40_000,
        url="http://virtual-home.org/",
        notes="Programmes d'activités quotidiennes sous forme de scripts de "
              "tâches — repéré dans l'enquête datasets (section 2).",
    ),
]


def total_budget() -> int:
    return sum(s.token_budget for s in CATALOG)


def by_family() -> dict:
    out: dict = {}
    for s in CATALOG:
        out.setdefault(s.family, []).append(s)
    return out
