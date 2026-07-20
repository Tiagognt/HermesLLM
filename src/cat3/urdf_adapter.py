"""
Voie URDF de la phase 2.

Chaîne : URDF -> capacités déterministes (urdf_parser) -> description en
langage naturel (LLM ou gabarit) -> garde-fou anti-hallucination ->
DocumentDraft dont le champ text = description + squelette de syntaxe.

Deux modes :
  - LLM (use_llm=True) : la description est rédigée par le fournisseur
    configuré ; on VÉRIFIE ensuite que tout chiffre du texte correspond à
    une grandeur extraite. Si le garde-fou échoue, on retombe sur le
    gabarit déterministe (jamais de chiffre halluciné dans le corpus).
  - gabarit (use_llm=False ou fournisseur "template") : description
    déterministe construite uniquement à partir des grandeurs extraites.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from urdf_parser import parse_urdf, derive_capabilities, make_skeleton
from llm_provider import LLMProvider, TemplateProvider, verify_numbers
from corpus_assembler import DocumentDraft


SYSTEM_PROMPT = (
    "You write concise, factual capability summaries of robots for a "
    "technical training corpus. Use ONLY the numeric values provided; never "
    "invent or infer numbers. Write 4-8 sentences, plain technical English."
)


def _allowed_numbers(cap: dict) -> List[float]:
    vals: List[float] = []
    for k, v in cap.items():
        if isinstance(v, (int, float)):
            vals.append(float(v))
        elif isinstance(v, dict):  # joint_types counts
            vals.extend(float(x) for x in v.values() if isinstance(x, (int, float)))
    return vals


def render_template(cap: dict) -> str:
    """Description déterministe, uniquement à partir des grandeurs extraites."""
    parts = []
    name = cap.get("robot_name", "This robot")
    parts.append(
        f"{name} is described by a URDF model with {cap['n_links']} links "
        f"and {cap['n_joints']} joints, totalling {cap['dof']} degrees of freedom "
        f"across {cap['actuated_joint_count']} actuated joints."
    )
    jt = ", ".join(f"{n} {t}" for t, n in cap.get("joint_types", {}).items())
    if jt:
        parts.append(f"Its joints break down as: {jt}.")
    if cap.get("total_mass_kg") is not None:
        parts.append(f"The summed link mass is {cap['total_mass_kg']} kg.")
    if cap.get("max_joint_effort") is not None:
        parts.append(f"The strongest actuated joint is rated at {cap['max_joint_effort']} "
                     f"(effort units as declared in the URDF).")
    if cap.get("max_joint_velocity") is not None:
        parts.append(f"The highest declared joint velocity limit is {cap['max_joint_velocity']}.")
    if cap.get("kinematic_span_m") is not None:
        parts.append(f"At its zero configuration the kinematic structure spans about "
                     f"{cap['kinematic_span_m']} m from the base link (an extent proxy, "
                     f"not a sampled workspace).")
    parts.append(f"The kinematic tree is rooted at link '{cap.get('root_link')}' "
                 f"and has {cap['n_leaf_links']} leaf links.")
    return " ".join(parts)


def _build_prompt(cap: dict) -> str:
    lines = ["Write a capability summary of this robot using ONLY these values:"]
    for k, v in cap.items():
        lines.append(f"- {k}: {v}")
    lines.append("\nDo not introduce any number that is not listed above.")
    return "\n".join(lines)


def describe(cap: dict, provider: LLMProvider) -> str:
    """Renvoie une description dont les chiffres sont garantis non hallucinés."""
    if isinstance(provider, TemplateProvider):
        return render_template(cap)

    text = provider.generate(_build_prompt(cap), system=SYSTEM_PROMPT)
    ok, offending = verify_numbers(text, _allowed_numbers(cap))
    if not ok:
        # Le LLM a introduit un/des chiffre(s) non extrait(s) -> on ne prend
        # AUCUN risque sur les chiffres du corpus : repli déterministe.
        return render_template(cap)
    return text.strip()


def adapt(
    robot_id: str,
    urdf_path: Path,
    *,
    license_status: str,
    url: str = "",
    source_name: str = "robot_descriptions",
    provider: Optional[LLMProvider] = None,
    skeleton_max_joints: Optional[int] = 60,
) -> DocumentDraft:
    provider = provider or TemplateProvider()
    model = parse_urdf(urdf_path)
    cap = derive_capabilities(model)
    description = describe(cap, provider)
    skeleton = make_skeleton(model, max_joints=skeleton_max_joints)

    text = f"{description}\n\n```urdf\n{skeleton}\n```"

    return DocumentDraft(
        robot_id=robot_id,
        source_type="urdf",
        text=text,
        license_status=license_status,
        url=url,
        lang="en",
        source_name=source_name,
        provenance={"capabilities": cap},
    )
