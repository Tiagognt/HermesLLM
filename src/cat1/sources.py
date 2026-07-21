"""
Declarative catalogue of category-1 sources (General Robot Data, tier A).

Adding a source = adding an entry here. This is the ONLY file in cat1 that
contains hard-coded repository names, mirroring `cat3/sources.py` for
robots.

--------------------------------------------------------------------------
LICENSES
Every `license_spdx` below was verified by hand on 2026-07-21 by reading
the repository's LICENSE file (the GitHub API returned `NOASSERTION` for
several of them -- navigation2, PythonRobotics, OMPL and PX4-user_guide --
all of which are in fact compliant). `collect_docs.py` re-reads that file
at collection time and REPORTS any disagreement with the value declared
here: the catalogue is authoritative, but a discrepancy is never silent.

Rejected after verification, and why:
  ros-infrastructure/rep          no LICENSE         -> no-license
  ros/ros_tutorials               no LICENSE         -> no-license
  ros-simulation/gazebo_ros_pkgs  no LICENSE         -> no-license
  OpenGVLab/Instruct2Act          no LICENSE         -> no-license
  NVlabs/progprompt-vh            NVIDIA License     -> outside allowlist
  SteveMacenski/slam_toolbox      LGPL-2.1           -> outside allowlist
  bulletphysics/bullet3           zlib               -> outside allowlist
Two of the three "planning-as-code" sources named in the brief (ProgPrompt,
Instruct2Act) are therefore unusable: only Code-as-Policies survives.

--------------------------------------------------------------------------
QUOTAS
`token_budget` is a CAP applied in phase 2, after deduplication. It exists
because the available volume far exceeds the target: the ROS 2
documentation alone weighs ~1.18 M tokens, i.e. the majority of cat1 by
itself. Without a cap the corpus would take on the style of a single
source. The budgets are therefore a DIVERSITY tool, not a volume one.

Adjusting the final size of cat1 = changing these numbers and re-running
phase 2. No re-collection is needed.
--------------------------------------------------------------------------
"""

from dataclasses import dataclass, field
from typing import List, Optional

# Content natures (= the <kind> level of data/cat1/raw/<kind>/<source_id>/)
KIND_DOCS = "docs"
KIND_INTERFACES = "interfaces"
KIND_CODE = "code"
KIND_NOTEBOOKS = "notebooks"


@dataclass
class RepoSource:
    source_id: str               # stable internal identifier
    display_name: str
    family: str                  # grouping, for stats and diversity
    kind: str                    # KIND_*
    repo_url: str
    repo_ref: str
    license_spdx: str            # hand-verified (see header)
    include_globs: List[str]
    token_budget: int
    exclude_globs: List[str] = field(default_factory=list)
    sparse_paths: Optional[List[str]] = None
    url: str = ""                # human-facing page, for the corpus `url` field
    notes: str = ""


# Exclusions common to every repository: tooling noise, not content.
COMMON_EXCLUDES = [
    ".github/*", "*/.github/*", "_static/*", "*/_static/*",
    "CHANGELOG*", "*/CHANGELOG*", "CONTRIBUTING*", "CODE_OF_CONDUCT*",
]


CATALOG: List[RepoSource] = [

    # ======================================================================
    # FAMILY "ros_docs" -- the ROS knowledge base.
    # Deliberately capped: these repositories could fill the whole of cat1
    # on their own and drown out the rest of the corpus.
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
        notes="~1.18 M tokens available, capped at 300k for diversity. "
              "Release notes (Releases/) are excluded: highly repetitive "
              "from one distribution to the next.",
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
        notes="Autonomous navigation: configuration, behaviour trees, "
              "plugins. Directly useful to per-robot planning.",
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
        notes="Manipulation: motion planning, kinematics, grasping.",
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
        notes="RATIONALE prose (why a given abstraction exists), not "
              "tutorials. High conceptual density, a register absent from "
              "the rest of the corpus.",
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
        notes="Hardware command layer: the link between planning and "
              "actuators.",
    ),

    # ======================================================================
    # FAMILY "sim_docs" -- simulator documentation.
    # Priority raised at the user's request: training will involve
    # sim-to-real, so being able to describe and drive a simulator is part
    # of the useful knowledge.
    # ======================================================================
    RepoSource(
        source_id="gazebo_docs", display_name="Gazebo Documentation",
        family="sim_docs", kind=KIND_DOCS,
        repo_url="https://github.com/gazebosim/docs.git",
        repo_ref="master", license_spdx="CC-BY-4.0",
        # The repository publishes 12 versions in parallel (citadel,
        # fortress, garden, harmonic, ionic, jetty...) with ~85% shared
        # content. We take ONLY the harmonic LTS plus the common trunk;
        # leaving the others in would push all the work onto the
        # deduplicator.
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
        notes="Physical modelling: contacts, actuators, sensors. "
              "Complements the cat3 URDFs.",
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
        notes="Multibody dynamics and optimisation -- the control side that "
              "the ROS documentation barely covers.",
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
        notes="The DRONE side, missing from cat1 even though the target "
              "fleet includes one. Flight modes, missions, safety, SITL "
              "simulation -- the aerial counterpart of what Nav2 brings on "
              "the ground.",
    ),

    # ======================================================================
    # FAMILY "interfaces" -- .msg / .srv / .action.
    # The item most directly useful to step (4), "action-function
    # selection": these are literally the command vocabulary the model will
    # have to emit. Small volume, maximum density.
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
              "The license is carried by each package (no root LICENSE).",
    ),
    RepoSource(
        source_id="nav2_msgs", display_name="Nav2 Interfaces",
        family="interfaces", kind=KIND_INTERFACES,
        repo_url="https://github.com/ros-navigation/navigation2.git",
        repo_ref="main", license_spdx="Apache-2.0",
        include_globs=["**/msg/*.msg", "**/srv/*.srv", "**/action/*.action"],
        token_budget=25_000,
        url="https://github.com/ros-navigation/navigation2",
        notes="NavigateToPose, ComputePathToPose, FollowWaypoints: the "
              "high-level navigation actions. The repository LICENSE reads "
              "'Apache-2.0 AND BSD-3-Clause', defaulting to Apache-2.0.",
    ),
    RepoSource(
        source_id="control_msgs", display_name="control_msgs",
        family="interfaces", kind=KIND_INTERFACES,
        repo_url="https://github.com/ros-controls/control_msgs.git",
        repo_ref="master", license_spdx="BSD-3-Clause",
        include_globs=["**/msg/*.msg", "**/srv/*.srv", "**/action/*.action"],
        token_budget=20_000,
        url="https://github.com/ros-controls/control_msgs",
        notes="FollowJointTrajectory, GripperCommand: joint-level command.",
    ),
    RepoSource(
        source_id="moveit_msgs", display_name="moveit_msgs",
        family="interfaces", kind=KIND_INTERFACES,
        repo_url="https://github.com/moveit/moveit_msgs.git",
        repo_ref="ros2", license_spdx="BSD-3-Clause",
        include_globs=["**/msg/*.msg", "**/srv/*.srv", "**/action/*.action"],
        token_budget=25_000,
        url="https://github.com/moveit/moveit_msgs",
        notes="MoveGroup, Grasp, CollisionObject: planned manipulation.",
    ),

    # ======================================================================
    # FAMILY "algorithms" -- documented robotics algorithms.
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
        notes="Path planning, SLAM, localisation, control -- every "
              "algorithm is written to be read.",
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
        notes="Companion library of the reference textbook: kinematics, "
              "dynamics, trajectory generation, with teaching docstrings.",
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
        notes="Sampling-based motion planning: RRT, PRM... the algorithmic "
              "foundation underneath MoveIt.",
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
        notes="Rigid-body dynamics -- consumes directly the URDFs collected "
              "in cat3.",
    ),

    # ======================================================================
    # FAMILY "examples" -- code written to be read (nodes, patterns).
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
        notes="Canonical patterns: publisher/subscriber, service, action, "
              "parameters. This is the shape a 'ROS node' must take.",
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
        notes="DECOMPOSITION of a manipulation task into stages -- on the "
              "manipulation side, the closest thing to what cat2 brings for "
              "multi-robot allocation.",
    ),
    # Behaviour trees are the EXECUTION model of per-robot planning (Nav2
    # uses them for its BT Navigator). No source covered them, even though
    # that is exactly step (3), "per-robot task planning", of the target.
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
        notes="Behaviour-tree library used by Nav2's BT Navigator. The prose "
              "documentation lives on a separate site (no public source "
              "repository), so we take the examples, which are written to "
              "be read.",
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
        notes="The prose side of behaviour trees: terminology, idioms, "
              "composites, decorators. Complements BehaviorTree.CPP, which "
              "only brings code.",
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
    # FAMILY "planning_code" -- natural language -> planning code.
    # Explicitly requested by the brief, but very thin in practice: see the
    # exclusions in the header.
    # ======================================================================
    RepoSource(
        source_id="code_as_policies", display_name="Code as Policies",
        family="planning_code", kind=KIND_NOTEBOOKS,
        repo_url="https://github.com/google-research/google-research.git",
        repo_ref="master", license_spdx="Apache-2.0",
        include_globs=["code_as_policies/**/*.ipynb", "code_as_policies/**/*.md"],
        # Multi-GB monolithic repository: sparse checkout is mandatory.
        # /LICENSE is materialised too, otherwise the license cross-check
        # finds nothing and reports a false problem.
        sparse_paths=["code_as_policies", "LICENSE"],
        token_budget=30_000,
        url="https://code-as-policies.github.io/",
        notes="The only one of the brief's three planning-as-code sources "
              "under a compliant license (ProgPrompt = NVIDIA License, "
              "Instruct2Act = no license at all).",
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
        notes="Formal representation of planning problems (PDDL, actions, "
              "preconditions, effects): the bridge between natural language "
              "and an executable plan.",
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
        notes="Daily-activity programs expressed as task scripts -- spotted "
              "in the project's dataset survey (section 2).",
    ),
]


def total_budget() -> int:
    return sum(s.token_budget for s in CATALOG)


def by_family() -> dict:
    out: dict = {}
    for s in CATALOG:
        out.setdefault(s.family, []).append(s)
    return out
