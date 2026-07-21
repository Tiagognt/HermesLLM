"""
Catalogue déclaratif des sources de la catégorie 2 (HMRS Data, tier B).

C'est le SEUL fichier de cat2 contenant des noms de dépôts et des
identifiants arXiv en dur, sur le modèle de `cat1/sources.py` et
`cat3/sources.py`.

cat2 est la catégorie la plus pauvre en sources : l'enquête datasets du
projet note que RoCoBench est « quasiment la seule source textuelle
multi-robots propre ». Elle est donc alimentée par TROIS voies
complémentaires plutôt qu'une seule :

  1. dépôts de frameworks et benchmarks HMRS (prompts, définitions de
     tâches, code de planification) ;
  2. le livre « Programming Multiple Robots with ROS 2 » (CC-BY-4.0), seul
     ouvrage complet sur le sujet ;
  3. des ARTICLES DE RECHERCHE, qui portent le vocabulaire du domaine
     (allocation, coalition, décomposition, embodiment-aware) que ni le
     code ni la documentation n'emploient.

--------------------------------------------------------------------------
LICENCES -- vérifiées à la main le 2026-07-21.

Dépôts écartés après lecture :
  SMARTlab-Purdue/SMART-LLM        aucun LICENSE  -> no-license
  UMass-Foundation-Model/Co-LLM-Agents (CoELA)  aucun LICENSE -> no-license
  facebookresearch/habitat-lab     MIT, mais ÉCARTÉ pour une autre raison :
                                   SgtVincent/EMOS en est un fork complet,
                                   les collecter tous deux dupliquerait
                                   l'intégralité du simulateur.

ARTICLES : arXiv publie la licence de chaque dépôt via son interface
OAI-PMH. Sur 148 articles pertinents interrogés :
    83  licence arXiv par défaut (nonexclusive-distrib) -> NON redistribuable
    45  CC-BY-4.0                                       -> conformes
     9  CC-BY-NC-ND-4.0                                 -> hors allowlist
     4  CC-BY-NC-SA-4.0                                 -> hors allowlist
     4  CC-BY-SA-4.0                                    -> hors allowlist (*)
     3  CC0-1.0                                         -> hors allowlist (*)
Seuls les 45 CC-BY-4.0 sont retenus (moins 2 hors sujet -> 43).
(*) CC-BY-SA et CC0 ne figurent pas dans l'allowlist du projet
    (`^CC-BY-\d\.\d$`). CC0 est pourtant PLUS permissif que CC-BY : les
    inclure demanderait d'élargir `license_utils.py`, ce qui ne se fait pas
    sans décision explicite. Gain potentiel : 7 articles.
--------------------------------------------------------------------------

QUOTAS : comme en cat1, `token_budget` est un plafond appliqué en phase 2.
La fenêtre cible de cat2 est étroite (elle est imposée par les tailles déjà
figées de cat1 et cat3), d'où des plafonds resserrés.
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
    fetch: str = "html"      # "html" (rendu arXiv) | "pdf" (repli poppler)

    @property
    def url(self) -> str:
        return f"https://arxiv.org/abs/{self.arxiv_id}"


COMMON_EXCLUDES = [
    ".github/*", "*/.github/*", "CHANGELOG*", "*/CHANGELOG*",
    "CONTRIBUTING*", "CODE_OF_CONDUCT*", "third_party/*",
]

# Licence commune à tous les articles retenus (vérifiée une par une).
PAPER_LICENSE_SPDX = "CC-BY-4.0"
PAPER_TOKEN_BUDGET = 280_000


REPO_CATALOG: List[RepoSource] = [

    # ======================================================================
    # FAMILLE « hmrs_framework » -- frameworks et benchmarks multi-robots.
    # Ce sont les seules sources qui contiennent des PROMPTS et des
    # définitions de tâches réellement multi-agents.
    # ======================================================================
    RepoSource(
        source_id="emos", display_name="EMOS / Habitat-MAS",
        family="hmrs_framework", kind=KIND_CODE,
        repo_url="https://github.com/SgtVincent/EMOS.git",
        repo_ref="main", license_spdx="MIT",
        # On restreint aux parties propres à EMOS : le reste du dépôt est un
        # fork de habitat-lab (simulateur), hors sujet pour cat2.
        include_globs=["docs/**/*.md", "*.md", "habitat-baselines/**/*.md",
                       "examples/**/*.md"],
        exclude_globs=COMMON_EXCLUDES,
        token_budget=35_000,
        url="https://github.com/SgtVincent/EMOS",
        notes="Méthodologie « Robot Resume » : URDF -> description de "
              "capacités -> allocation embodiment-aware. C'est exactement le "
              "pont entre cat3 et la cible du modèle.",
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
        notes="Dialogue dialectique entre robots : les prompts de "
              "négociation et les six tâches de RoCoBench. Source textuelle "
              "multi-robots la plus propre selon l'enquête datasets.",
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
        notes="100 k tâches de collaboration ; le planificateur LLM "
              "(habitat_llm) contient les prompts de décomposition et "
              "d'assignation.",
    ),

    # ======================================================================
    # FAMILLE « hmrs_book » -- le seul ouvrage complet du domaine.
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
        notes="Livre de l'Open Source Robotics Foundation : flottes "
              "hétérogènes, répartition des tâches, interopérabilité. Prose "
              "pédagogique continue, registre absent des autres sources.",
    ),

    # ======================================================================
    # FAMILLE « fleet » -- gestion de flotte hétérogène en production.
    # Contrepoint indispensable aux articles : ici l'allocation de tâches
    # n'est pas une expérience, c'est un système déployé.
    # ======================================================================
    RepoSource(
        source_id="open_rmf", display_name="Open-RMF",
        family="fleet", kind=KIND_DOCS,
        repo_url="https://github.com/open-rmf/rmf.git",
        repo_ref="main", license_spdx="Apache-2.0",
        # `reports/` contient les tableaux de statut d'intégration continue
        # (281 000 caractères de badges pour un seul fichier) : du bruit
        # d'outillage, aucune connaissance robotique. Exclu.
        include_globs=["docs/**/*.md", "*.md"],
        exclude_globs=COMMON_EXCLUDES + ["reports/*"],
        token_budget=40_000,
        url="https://www.open-rmf.org/",
        notes="Interopérabilité entre flottes de robots hétérogènes, "
              "allocation de tâches et résolution de conflits sur des "
              "ressources partagées (ascenseurs, portes, couloirs).",
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
        notes="Tâches concrètes de flotte (livraison, boucle de patrouille, "
              "nettoyage) et adaptateurs de flotte.",
    ),
]


# ==========================================================================
# ARTICLES DE RECHERCHE -- tous CC-BY-4.0, licence vérifiée une par une via
# l'interface OAI-PMH d'arXiv (champ <license> de la notice).
# `fetch` indique la voie d'extraction : "html" quand arXiv publie un rendu
# HTML (net et structuré), "pdf" sinon (articles antérieurs à fin 2023).
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
