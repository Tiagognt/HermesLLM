"""
Declarative catalogue of category-2 sources (HMRS Data, tier B).

This is the ONLY file in cat2 containing hard-coded repository names and
arXiv identifiers, mirroring `cat1/sources.py` and `cat3/sources.py`.

cat2 is the category with the fewest available sources: the project's
dataset survey notes that RoCoBench is "almost the only clean multi-robot
text source". It is therefore fed by THREE complementary paths rather than
one:

  1. repositories of HMRS frameworks and benchmarks (prompts, task
     definitions, planning code);
  2. the book "Programming Multiple Robots with ROS 2" (CC-BY-4.0), the
     only complete work on the subject;
  3. RESEARCH PAPERS, which carry the vocabulary of the field (allocation,
     coalition, decomposition, embodiment-aware) that neither code nor
     documentation uses.

--------------------------------------------------------------------------
LICENSES -- verified by hand on 2026-07-21.

Repositories rejected after reading:
  SMARTlab-Purdue/SMART-LLM         no LICENSE -> no-license
  UMass-Foundation-Model/Co-LLM-Agents (CoELA)  no LICENSE -> no-license
  facebookresearch/habitat-lab      MIT, but REJECTED for a different
                                    reason: SgtVincent/EMOS is a complete
                                    fork of it, so collecting both would
                                    duplicate the whole simulator.

PAPERS: arXiv publishes the license of every submission through its OAI-PMH
interface. Of 148 relevant papers queried:
    83  arXiv default license (nonexclusive-distrib) -> NOT redistributable
    45  CC-BY-4.0                                    -> compliant
     9  CC-BY-NC-ND-4.0                              -> outside allowlist
     4  CC-BY-NC-SA-4.0                              -> outside allowlist
     4  CC-BY-SA-4.0                                 -> outside allowlist (*)
     3  CC0-1.0                                      -> outside allowlist (*)
Only the 45 CC-BY-4.0 papers are retained (minus 2 off-topic -> 43).
(*) CC-BY-SA and CC0 are not on the project allowlist (`^CC-BY-\d\.\d$`).
    CC0 is nevertheless MORE permissive than CC-BY: including them would
    require widening `license_utils.py`, which is not done without an
    explicit decision. Potential gain: 7 papers.
--------------------------------------------------------------------------

QUOTAS: as in cat1, `token_budget` is a cap applied in phase 2. The cat2
target window is narrow (it is imposed by the already-fixed sizes of cat1
and cat3), hence the tight caps.
"""

from dataclasses import dataclass, field
from typing import List, Optional

KIND_DOCS = "docs"
KIND_CODE = "code"
KIND_PAPER = "paper"


@dataclass
class RepoSource:
    source_id: str
    display_name: str
    family: str
    kind: str
    repo_url: str
    repo_ref: str
    license_spdx: str
    include_globs: List[str]
    token_budget: int
    exclude_globs: List[str] = field(default_factory=list)
    sparse_paths: Optional[List[str]] = None
    url: str = ""
    notes: str = ""


@dataclass
class Paper:
    arxiv_id: str
    title: str
    fetch: str = "html"      # "html" (arXiv rendering) | "pdf" (poppler fallback)

    @property
    def url(self) -> str:
        return f"https://arxiv.org/abs/{self.arxiv_id}"


COMMON_EXCLUDES = [
    ".github/*", "*/.github/*", "CHANGELOG*", "*/CHANGELOG*",
    "CONTRIBUTING*", "CODE_OF_CONDUCT*", "third_party/*",
]

# License shared by every retained paper (verified one by one).
PAPER_LICENSE_SPDX = "CC-BY-4.0"
PAPER_TOKEN_BUDGET = 280_000


REPO_CATALOG: List[RepoSource] = [

    # ======================================================================
    # FAMILY "hmrs_framework" -- multi-robot frameworks and benchmarks.
    # These are the only sources that contain genuinely multi-agent PROMPTS
    # and task definitions.
    # ======================================================================
    RepoSource(
        source_id="emos", display_name="EMOS / Habitat-MAS",
        family="hmrs_framework", kind=KIND_CODE,
        repo_url="https://github.com/SgtVincent/EMOS.git",
        repo_ref="main", license_spdx="MIT",
        # Restricted to the parts specific to EMOS: the rest of the
        # repository is a fork of habitat-lab (the simulator), off-topic
        # for cat2.
        include_globs=["docs/**/*.md", "*.md", "habitat-baselines/**/*.md",
                       "examples/**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=35_000,
        url="https://github.com/SgtVincent/EMOS",
        notes="The 'Robot Resume' methodology: URDF -> capability "
              "description -> embodiment-aware allocation. This is exactly "
              "the bridge between cat3 and the model's target behaviour.",
    ),
    RepoSource(
        source_id="roco", display_name="RoCo / RoCoBench",
        family="hmrs_framework", kind=KIND_CODE,
        repo_url="https://github.com/MandiZhao/robot-collab.git",
        repo_ref="main", license_spdx="MIT",
        include_globs=["rocobench/**/*.py", "prompting/**/*.py", "*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=45_000,
        url="https://project-roco.github.io/",
        notes="Dialectic negotiation between robots: the negotiation "
              "prompts and the six RoCoBench tasks. The cleanest "
              "multi-robot text source according to the dataset survey.",
    ),
    RepoSource(
        source_id="partnr", display_name="PARTNR (Meta)",
        family="hmrs_framework", kind=KIND_CODE,
        repo_url="https://github.com/facebookresearch/partnr-planner.git",
        repo_ref="main", license_spdx="MIT",
        include_globs=["docs/**/*.md", "*.md", "habitat_llm/**/*.py",
                       "dataset_generation/**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=50_000,
        url="https://github.com/facebookresearch/partnr-planner",
        notes="100k collaboration tasks; the LLM planner (habitat_llm) "
              "holds the decomposition and assignment prompts.",
    ),

    # ======================================================================
    # FAMILY "hmrs_book" -- the only complete work in the field.
    # ======================================================================
    RepoSource(
        source_id="ros2_multirobot_book",
        display_name="Programming Multiple Robots with ROS 2",
        family="hmrs_book", kind=KIND_DOCS,
        repo_url="https://github.com/osrf/ros2multirobotbook.git",
        repo_ref="master", license_spdx="CC-BY-4.0",
        include_globs=["src/**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=75_000,
        url="https://osrf.github.io/ros2multirobotbook/",
        notes="Book by the Open Source Robotics Foundation: heterogeneous "
              "fleets, task distribution, interoperability. Continuous "
              "teaching prose, a register absent from the other sources.",
    ),

    # ======================================================================
    # FAMILY "fleet" -- heterogeneous fleet management in production.
    # An indispensable counterpoint to the papers: here task allocation is
    # not an experiment, it is a deployed system.
    # ======================================================================
    RepoSource(
        source_id="open_rmf", display_name="Open-RMF",
        family="fleet", kind=KIND_DOCS,
        repo_url="https://github.com/open-rmf/rmf.git",
        repo_ref="main", license_spdx="Apache-2.0",
        # `reports/` holds continuous-integration status tables (281,000
        # characters of badges in a single file): tooling noise, no
        # robotics knowledge. Excluded.
        include_globs=["docs/**/*.md", "*.md"],
        exclude_globs=COMMON_EXCLUDES + ["reports/*"],
        token_budget=40_000,
        url="https://www.open-rmf.org/",
        notes="Interoperability between heterogeneous robot fleets, task "
              "allocation and conflict resolution over shared resources "
              "(lifts, doors, corridors).",
    ),
    RepoSource(
        source_id="rmf_demos", display_name="Open-RMF Demos",
        family="fleet", kind=KIND_CODE,
        repo_url="https://github.com/open-rmf/rmf_demos.git",
        repo_ref="main", license_spdx="Apache-2.0",
        include_globs=["docs/**/*.md", "*.md", "rmf_demos_tasks/**/*.py",
                       "rmf_demos_fleet_adapter/**/*.py"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=35_000,
        url="https://github.com/open-rmf/rmf_demos",
        notes="Concrete fleet tasks (delivery, patrol loop, cleaning) and "
              "fleet adapters.",
    ),
]


# ==========================================================================
# RESEARCH PAPERS -- all CC-BY-4.0, license verified one by one through the
# arXiv OAI-PMH interface (the <license> field of the record).
# `fetch` gives the extraction path: "html" when arXiv publishes an HTML
# rendering (clean and structured), "pdf" otherwise (papers predating late
# 2023).
# ==========================================================================

PAPER_CATALOG: List[Paper] = [
    Paper("2104.01834", "Skyeye Team at MBZIRC 2020: A team of aerial and ground robots for GPS-denied autonomous fire...", "pdf"),
    Paper("2203.00947", "KC-TSS: An Algorithm for Heterogeneous Robot Teams Performing Resilient Target Search", "pdf"),
    Paper("2208.06053", "Adaptive Sampling of Latent Phenomena using Heterogeneous Robot Teams (ASLaP-HR)", "pdf"),
    Paper("2209.02865", "DC-MRTA: Decentralized Multi-Robot Task Allocation and Navigation in Complex Environments", "pdf"),
    Paper("2209.05738", "RTAW: An Attention Inspired Reinforcement Learning Method for Multi-Robot Task Allocation in ...", "pdf"),
    Paper("2209.14040", "Scheduling of Missions with Constrained Tasks for Heterogeneous Robot Systems", "pdf"),
    Paper("2308.01552", "InterAct: Exploring the Potentials of ChatGPT as a Cooperative Agent", "pdf"),
    Paper("2309.10062", "SMART-LLM: Smart Multi-Agent Robot Task Planning using Large Language Models", "html"),
    Paper("2310.02071", "Towards End-to-End Embodied Decision Making via Multi-modal Large Language Model: Exploration...", "html"),
    Paper("2310.04572", "LIVE: Lidar Informed Visual Search for Multiple Objects with Multiple Robots", "html"),
    Paper("2403.11737", "SMT-Based Dynamic Multi-Robot Task Allocation", "html"),
    Paper("2404.02318", "ZeroCAP: Zero-Shot Multi-Robot Context Aware Pattern Formation via Large Language Models", "html"),
    Paper("2404.10775", "COMBO: Compositional World Models for Embodied Multi-Agent Cooperation", "html"),
    Paper("2406.01915", "Enhancing Human-Robot Collaborative Assembly in Manufacturing Systems Using Large Language Mo...", "html"),
    Paper("2408.01877", "Improving Zero-Shot ObjectNav with Generative Communication", "pdf"),
    Paper("2408.05478", "Multi-Agent Planning Using Visual Language Models", "html"),
    Paper("2409.06531", "Multi-robot Task Allocation and Path Planning with Maximum Range Constraints", "html"),
    Paper("2409.16009", "Modeling and Evaluating Trust Dynamics in Multi-Human Multi-Robot Task Allocation", "html"),
    Paper("2410.14383", "MARLIN: Multi-Agent Reinforcement Learning Guided by Language-Based Inter-Robot Negotiation", "html"),
    Paper("2410.21040", "LiP-LLM: Integrating Linear Programming and dependency graph with Large Language Models for m...", "html"),
    Paper("2410.22662", "EMOS: Embodiment-aware Heterogeneous Multi-robot Operating System with LLM Agents", "html"),
    Paper("2411.02062", "Heterogeneous Multi-robot Task Allocation for Long-Endurance Missions in Dynamic Scenarios", "html"),
    Paper("2411.04679", "CaPo: Cooperative Plan Optimization for Efficient Embodied Multi-Agent Cooperation", "html"),
    Paper("2412.20397", "Learning Policies for Dynamic Coalition Formation in Multi-Robot Task Allocation", "html"),
    Paper("2502.03814", "Large Language Models for Multi-Robot Systems: A Survey", "html"),
    Paper("2502.16079", "Together We Rise: Optimizing Real-Time Multi-Robot Task Allocation using Coordinated Heteroge...", "html"),
    Paper("2503.17309", "LLM+MAP: Bimanual Robot Task Planning using Large Language Models and Planning Domain Definit...", "html"),
    Paper("2505.00820", "HMCF: A Human-in-the-loop Multi-Robot Collaboration Framework Based on Large Language Models", "html"),
    Paper("2505.13278", "Hybrid Voting-Based Task Assignment in Modular Construction Scenarios", "html"),
    Paper("2507.16068", "Compositional Coordination for Multi-Robot Teams with Large Language Models", "html"),
    Paper("2509.21020", "Hybrid Task and Motion Planning with Reactive Collision Handling for Multi-Robot Disassembly ...", "html"),
    Paper("2510.03153", "Improving Cooperation in Collaborative Embodied AI", "html"),
    Paper("2510.14063", "Adaptive Obstacle-Aware Task Assignment and Planning for Heterogeneous Robot Teaming", "html"),
    Paper("2512.00797", "Transforming Monolithic Foundation Models into Embodied Multi-Agent Architectures for Human-R...", "html"),
    Paper("2602.06967", "Leveraging Adaptive Group Negotiation for Heterogeneous Multi-Robot Collaboration with Large ...", "html"),
    Paper("2602.13866", "Modeling and Optimizing the Provisioning of Exhaustible Capabilities for Simultaneous Task Al...", "html"),
    Paper("2603.06898", "Collaborative Planning with Concurrent Synchronization for Operationally Constrained UAV-UGV ...", "html"),
    Paper("2603.15418", "MA-VLCM: A Vision Language Critic Model for Value Estimation of Policies in Multi-Agent Team ...", "html"),
    Paper("2603.30022", "Hybrid Framework for Robotic Manipulation: Integrating Reinforcement Learning and Large Langu...", "html"),
    Paper("2604.01213", "Collaborative Task and Path Planning for Heterogeneous Robotic Teams using Multi-Agent PPO", "html"),
    Paper("2604.06813", "Event-Triggered Adaptive Consensus for Multi-Robot Task Allocation", "html"),
    Paper("2605.25584", "Acting on the Unseen: Communication-Free Collaborative Filtering for Decentralized Multi-Robo...", "pdf"),
    Paper("2606.27929", "When Multi-Robot Systems Meet Agentic AI:Towards Embodied Collective Intelligence", "html"),
]


def total_budget() -> int:
    return sum(s.token_budget for s in REPO_CATALOG) + PAPER_TOKEN_BUDGET
