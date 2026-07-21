"""
Declarative catalogue of the robots to collect for category 3
(URDF & Robot Specs).

Adding a robot = adding an entry here. No other file needs to change to
scale to a new robot -- this is the only place in the pipeline that knows
hard-coded robot names.

SourceType.ROBOT_DESCRIPTIONS entries carry no hard-coded license: it is
read dynamically from robot_descriptions.py at collection time
(fetch_robot_descriptions.py), so it stays in sync with the source of
truth. `known_license_spdx` is only used for GIT_REPO entries, where no
automatic equivalent exists -- verified by hand (actual inspection of the
repository's LICENSE file).

`robot_class` follows the taxonomy used by robot_descriptions.py (arm,
quadruped, humanoid, biped, wheeled, mobile_manipulator, drone, dual_arm,
end_effector) to prepare the "embodiment" tag expected at the
transformation stage (embodiment-aware allocation).

--------------------------------------------------------------------------
COMPOSITION -- "complete robots only" rebalancing:
  - end effectors (grippers/hands) excluded;
  - a single dual-arm robot kept (Baxter);
  - biped / mobile / humanoid classes reinforced;
  - 4 sources outside robot_descriptions.py (direct git), each license
    verified by reading the repository's LICENSE file.

DIVERSITY -- the ten robots added on 2026-07-21 were chosen for
morphological and vendor diversity, not for volume. Forty-eight compliant
modules were available in robot_descriptions.py; the near-duplicate
families (8 Kinova Jaco2 variants, 10 Universal Robots variants, 5 ROBOTIS
OMY variants) were deliberately skipped: they would have added almost
duplicated volume, not knowledge.

All licenses (RD + git) are classified as compliant with the project
allowlist (MIT / BSD-x-Clause / Apache-2.0 / CC-BY-x.x). One assumed
exception: AgileX Ranger Mini (no license at all -> "no-license", collected
on an explicit project decision).
--------------------------------------------------------------------------
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class SourceType(Enum):
    # Retrieval through the robot_descriptions.py library: it handles the
    # clone, the cache, the Xacro -> URDF rendering when needed, and
    # exposes the declared license of the source repository.
    ROBOT_DESCRIPTIONS = "robot_descriptions"

    # Direct retrieval from a git repository (used when the robot is not in
    # the robot_descriptions.py catalogue).
    GIT_REPO = "git_repo"


@dataclass
class RobotSource:
    robot_id: str            # stable internal identifier, e.g. "unitree_g1"
    display_name: str        # readable name, e.g. "Unitree G1"
    source_type: SourceType
    robot_class: str = ""    # arm / quadruped / humanoid / biped / wheeled /
                             # mobile_manipulator / drone / dual_arm / end_effector
    fleet_priority: bool = False   # part of the priority fleet
    notes: str = ""

    # --- fields used when source_type == ROBOT_DESCRIPTIONS ---
    description_module: Optional[str] = None   # e.g. "g1_description"

    # --- fields used when source_type == GIT_REPO ---
    repo_url: Optional[str] = None
    repo_ref: Optional[str] = None                # branch to clone
    file_path_in_repo: Optional[str] = None       # path of the .urdf/.xacro
    known_license_spdx: Optional[str] = None      # None if no license found


def _rd(robot_id, display_name, description_module, robot_class,
        fleet_priority=False, notes=""):
    """Shortcut for a ROBOT_DESCRIPTIONS entry (the most frequent case)."""
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
    """Shortcut for a GIT_REPO entry (a source outside robot_descriptions.py)."""
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

    # ============ QUADRUPEDS (12) ============
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
    # -- added 2026-07-21: genuinely different actuation, not variants of
    #    what is already in the catalogue (see the "diversity" note above).
    _rd("hyq", "HyQ (IIT)", "hyq_description", "quadruped",
        notes="HYDRAULIC quadruped: joint efforts of a completely different "
              "order of magnitude from the electric quadrupeds already here."),
    _rd("minitaur", "Minitaur (Ghost Robotics)", "minitaur_description", "quadruped",
        notes="Direct-drive legs, five-bar linkage: a morphology absent from "
              "the rest of the catalogue."),

    # ============ HUMANOIDS (14) ============
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
    # -- added 2026-07-21: three makers absent from the catalogue.
    _rd("bxi_elf2", "BXI Elf2", "elf2_description", "humanoid"),
    _rd("fourier_n1", "Fourier N1", "n1_description", "humanoid",
        notes="Fourier GR family, cited by the dataset survey (section 6.1)."),
    _rd("sigmaban", "SigmaBan (Rhoban)", "sigmaban_description", "humanoid",
        notes="Small-scale humanoid (RoboCup): scale and masses far below "
              "the full-size humanoids in the catalogue."),
    # -- outside robot_descriptions.py: LICENSE read directly -> BSD-3-Clause
    _git("robotera_star1", "RobotEra STAR1", "humanoid",
         repo_url="https://github.com/roboterax/models.git",
         repo_ref="main",
         file_path_in_repo="star1/urdf/l3_with_hand_fixedpin_xml.urdf",
         known_license_spdx="BSD-3-Clause",
         notes="Direct URDF (no Xacro). BSD-3-Clause LICENSE verified by "
               "reading the file at the repository root."),

    # ============ BIPEDS (5) ============
    _rd("cassie", "Cassie", "cassie_description", "biped"),
    _rd("bolt", "Bolt", "bolt_description", "biped"),
    _rd("upkie", "Upkie", "upkie_description", "biped"),
    _rd("rhea", "Rhea", "rhea_description", "biped"),
    # -- outside robot_descriptions.py: LICENSE read directly -> Apache-2.0
    _git("robotis_op3", "ROBOTIS OP3", "biped",
         repo_url="https://github.com/ROBOTIS-GIT/ROBOTIS-OP3-Common.git",
         repo_ref="master",
         file_path_in_repo="op3_description/urdf/robotis_op3.urdf.xacro",
         known_license_spdx="Apache-2.0",
         notes="Self-contained Xacro (no external dependency). Apache-2.0 "
               "LICENSE verified by reading the file at the repository root."),

    # ============ WHEELED MOBILE (2 + Ranger Mini below) ============
    _rd("rsk_omnidirectional", "RSK Omnidirectional", "rsk_description", "wheeled"),
    # -- added 2026-07-21: the "wheeled" class only had 2 entries, the
    #    weakest in the catalogue. A wheeled-legged robot is also a hybrid
    #    morphology that no other entry covers.
    _rd("limx_wl_p311d", "LimX Dynamics WL P311D", "wl_p311d_description", "wheeled",
        notes="Wheeled-legged biped: hybrid locomotion, relevant to "
              "embodiment-aware allocation."),

    # ============ MANIPULATOR ARMS (16) ============
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
    # -- added 2026-07-21: four makers and four payload classes that were
    #    missing. Variants close to arms already present (8 Jaco2, 10 UR,
    #    5 OMY) were deliberately SKIPPED: they would add near-duplicated
    #    volume, not diversity.
    _rd("comau_edo", "Comau e.DO", "edo_description", "arm"),
    _rd("fanuc_m710ic", "Fanuc M-710iC", "fanuc_m710ic_description", "arm",
        notes="Heavy industrial arm: Fanuc, the world's largest maker, was "
              "represented by no entry at all."),
    _rd("flexiv_rizon4", "Flexiv Rizon 4", "rizon4_description", "arm",
        notes="Force-feedback arm (impedance control)."),
    _rd("so_arm100", "SO-ARM100 (The Robot Studio)", "so_arm100_description", "arm",
        notes="Low-cost open-source arm: efforts and masses of a completely "
              "different order from the industrial arms in the catalogue."),

    # ============ MOBILE MANIPULATORS (7) ============
    _rd("fetch", "Fetch", "fetch_description", "mobile_manipulator"),
    # The module is called "tiago_description" (not "tiago_official_description",
    # which does not exist in robot_descriptions: the previous entry crashed
    # with a ModuleNotFoundError and left no trace on disk). The name was
    # corrected so that the license barrier can do its job: TIAGo is
    # published under CC-BY-NC-ND-3.0, hence OUTSIDE the allowlist -> the
    # robot is now explicitly set aside and logged, instead of failing
    # silently.
    _rd("tiago", "TIAGo", "tiago_description", "mobile_manipulator",
        notes="CC-BY-NC-ND-3.0 license (NonCommercial + NoDerivatives): "
              "outside the project allowlist. Set aside by the license "
              "barrier, kept in the catalogue so the exclusion stays traced."),
    _rd("reachy", "Reachy", "reachy_description", "mobile_manipulator"),
    _rd("pepper", "Pepper", "pepper_description", "mobile_manipulator"),
    _rd("rby1", "RBY1", "rby1_description", "mobile_manipulator"),
    _rd("eve_r3", "Eve R3", "eve_r3_description", "mobile_manipulator"),
    _rd("bambot", "BamBot", "bambot_description", "mobile_manipulator"),

    # ============ DRONES (3) ============
    _rd("crazyflie2", "Crazyflie 2.0", "cf2_description", "drone"),
    _rd("skydio_x2", "Skydio X2", "skydio_x2_description", "drone"),
    # -- outside robot_descriptions.py: LICENSE read directly -> Apache-2.0
    _git("nasa_ingenuity", "NASA JPL Ingenuity", "drone",
         repo_url="https://github.com/david-dorf/perseverance-ingenuity-urdfs.git",
         repo_ref="main",
         file_path_in_repo="ingenuity/ingenuity.urdf",
         known_license_spdx="Apache-2.0",
         notes="Direct URDF (no Xacro). Apache-2.0 LICENSE verified by "
               "reading the file at the repository root."),

    # ============ DUAL ARM (1) ============
    _rd("baxter", "Baxter", "baxter_description", "dual_arm"),

    # ============ WHEELED GROUND VEHICLE -- outside robot_descriptions.py ====
    RobotSource(
        robot_id="agilex_ranger_mini_v3",
        display_name="AgileX Ranger Mini 3.0",
        source_type=SourceType.GIT_REPO,
        robot_class="wheeled",
        repo_url="https://github.com/agilexrobotics/ugv_gazebo_sim.git",
        repo_ref="master",
        file_path_in_repo="ranger_mini/ranger_mini_v3/urdf/ranger_mini.xacro",
        known_license_spdx=None,  # verified through the GitHub API on
                                  # 2026-07-15: no LICENSE file in the repo.
        fleet_priority=True,
        notes=(
            "No license declared in the source repository (verified through "
            "the GitHub API). Collected anyway with license_status="
            "'no-license', on an explicit project decision, to be revisited "
            "later (see the exchange of 2026-07-15)."
        ),
    ),
]

# NB: the set of robots whose missing license is tolerated
# (ALLOW_NO_LICENSE_FOR = {"agilex_ranger_mini_v3"}) currently lives in
# collect_pilot.py. None of the git robots added here needs to be listed
# there: they all have a verified compliant license. Do not duplicate that
# set here, to avoid it drifting from the one in collect_pilot.py.
