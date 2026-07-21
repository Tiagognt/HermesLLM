"""
Parsing déterministe d'un URDF vers une représentation intermédiaire
robot-agnostique, PUIS dérivation de capacités (DOF, masse, limites,
portée cinématique) et extraction d'un squelette de syntaxe nettoyé.

Principe clé du projet : TOUT chiffre du corpus final vient d'ici, par le
code, jamais d'un LLM. La description en langage naturel (module LLM,
séparé) ne fera que reformuler des valeurs déjà extraites ici -- et un
garde-fou vérifiera qu'elle n'invente aucun nombre.

Aucune dépendance ROS. math3d fait maison (pas de dépendance externe au-delà
de la lib standard) pour rester installable partout.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Degrés de liberté par type de joint URDF.
_DOF_BY_TYPE = {
    "revolute": 1,
    "continuous": 1,
    "prismatic": 1,
    "fixed": 0,
    "floating": 6,
    "planar": 3,
}
_ACTUATED_TYPES = {"revolute", "continuous", "prismatic"}


# --------------------------------------------------------------------------
# Représentation intermédiaire
# --------------------------------------------------------------------------

@dataclass
class JointLimit:
    lower: Optional[float] = None
    upper: Optional[float] = None
    effort: Optional[float] = None
    velocity: Optional[float] = None


@dataclass
class Joint:
    name: str
    type: str
    parent: str
    child: str
    axis: Optional[Tuple[float, float, float]] = None
    origin_xyz: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    origin_rpy: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    limit: Optional[JointLimit] = None


@dataclass
class Link:
    name: str
    mass: Optional[float] = None   # None si pas d'<inertial><mass>


@dataclass
class RobotModel:
    name: str
    links: List[Link] = field(default_factory=list)
    joints: List[Joint] = field(default_factory=list)
    # Réparations appliquées au XML avant parsing. Jamais silencieuses :
    # l'appelant les journalise (règle « aucun saut silencieux »).
    parse_notes: List[str] = field(default_factory=list)

    def link_names(self) -> List[str]:
        return [l.name for l in self.links]


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def _floats(text: Optional[str], n: int, default) -> Tuple:
    if not text:
        return default
    parts = text.strip().split()
    try:
        vals = tuple(float(p) for p in parts)
    except ValueError:
        return default
    return vals if len(vals) == n else default


def _opt_float(x: Optional[str]) -> Optional[float]:
    if x is None:
        return None
    try:
        return float(x)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Lecture XML tolérante aux préfixes de namespace non déclarés
#
# Certains URDF publiés à l'époque de Gazebo Classic contiennent des balises
# préfixées (<sensor:camera>, <controller:gazebo_ros_camera>) sans le
# xmlns: correspondant. C'est du XML invalide : ElementTree refuse le
# fichier entier avec « unbound prefix », et on perdait donc TOUT le robot
# (cas réel : fetch, ligne 655) alors que ses <link>/<joint> sont parfaits.
#
# On déclare donc les préfixes manquants sur l'élément racine avant de
# parser. Aucune donnée n'est supprimée ni réécrite : on n'ajoute que les
# déclarations xmlns absentes. Les éléments concernés se retrouvent dans un
# namespace factice, donc ignorés par nos findall("link")/findall("joint")
# non préfixés -- exactement le comportement voulu, puisque ce sont des
# extensions simulateur, pas de la description cinématique.
# --------------------------------------------------------------------------

_TAG_PREFIX_RE = re.compile(r"</?([A-Za-z_][\w.\-]*):")
_ATTR_PREFIX_RE = re.compile(r"\s([A-Za-z_][\w.\-]*):[\w.\-]+\s*=")
_XMLNS_DECL_RE = re.compile(r"xmlns:([A-Za-z_][\w.\-]*)\s*=")
_FIRST_ELEMENT_RE = re.compile(r"<([A-Za-z_][\w.\-]*)(\s|>|/)")

_RESERVED_PREFIXES = {"xml", "xmlns"}
_UNDECLARED_NS_FMT = "urn:hermes:undeclared:{}"


def _undeclared_prefixes(raw: str) -> List[str]:
    used = set(_TAG_PREFIX_RE.findall(raw)) | set(_ATTR_PREFIX_RE.findall(raw))
    declared = set(_XMLNS_DECL_RE.findall(raw))
    return sorted(used - declared - _RESERVED_PREFIXES)


def _declare_prefixes(raw: str, prefixes: List[str]) -> str:
    m = _FIRST_ELEMENT_RE.search(raw)
    if m is None:
        raise ET.ParseError("aucun élément racine trouvé dans le document")
    decls = " " + " ".join(
        f'xmlns:{p}="{_UNDECLARED_NS_FMT.format(p)}"' for p in prefixes)
    insert_at = m.end(1)
    return raw[:insert_at] + decls + raw[insert_at:]


def read_urdf_xml(path: Path) -> Tuple[ET.Element, List[str]]:
    """
    Retourne (racine, notes). `notes` documente toute réparation appliquée.
    Une erreur XML qui n'est pas un préfixe non déclaré est relayée telle
    quelle : on ne répare que ce qu'on sait réparer sans rien inventer.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        return ET.fromstring(raw), []
    except ET.ParseError as first_error:
        if "unbound prefix" not in str(first_error):
            raise
        prefixes = _undeclared_prefixes(raw)
        if not prefixes:
            raise
        root = ET.fromstring(_declare_prefixes(raw, prefixes))
        note = (f"XML réparé avant parsing : préfixe(s) de namespace non "
                f"déclaré(s) {prefixes} (erreur d'origine : {first_error}). "
                f"Déclarations xmlns ajoutées sur la racine ; les éléments "
                f"concernés (extensions simulateur) sont ignorés.")
        return root, [note]


def parse_urdf(path: Path) -> RobotModel:
    """Lit un fichier URDF et renvoie un RobotModel. Robuste aux champs absents."""
    root, notes = read_urdf_xml(path)
    model = RobotModel(name=root.get("name", "unnamed"), parse_notes=notes)

    for l in root.findall("link"):
        mass_el = l.find("inertial/mass")
        mass = _opt_float(mass_el.get("value")) if mass_el is not None else None
        model.links.append(Link(name=l.get("name", ""), mass=mass))

    for j in root.findall("joint"):
        parent_el, child_el = j.find("parent"), j.find("child")
        origin_el = j.find("origin")
        axis_el = j.find("axis")
        limit_el = j.find("limit")

        limit = None
        if limit_el is not None:
            limit = JointLimit(
                lower=_opt_float(limit_el.get("lower")),
                upper=_opt_float(limit_el.get("upper")),
                effort=_opt_float(limit_el.get("effort")),
                velocity=_opt_float(limit_el.get("velocity")),
            )

        model.joints.append(Joint(
            name=j.get("name", ""),
            type=j.get("type", "fixed"),
            parent=parent_el.get("link") if parent_el is not None else "",
            child=child_el.get("link") if child_el is not None else "",
            axis=_floats(axis_el.get("xyz") if axis_el is not None else None, 3, None),
            origin_xyz=_floats(origin_el.get("xyz") if origin_el is not None else None, 3, (0.0, 0.0, 0.0)),
            origin_rpy=_floats(origin_el.get("rpy") if origin_el is not None else None, 3, (0.0, 0.0, 0.0)),
            limit=limit,
        ))
    return model


# --------------------------------------------------------------------------
# Petite algèbre 3D (pas de numpy requis)
# --------------------------------------------------------------------------

def _rpy_to_matrix(r: float, p: float, y: float) -> List[List[float]]:
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    # R = Rz(y) @ Ry(p) @ Rx(r)  (convention URDF)
    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp,     cp * sr,                cp * cr],
    ]


def _mat_vec(m, v):
    return tuple(m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3))


def _mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


# --------------------------------------------------------------------------
# Dérivation de capacités (déterministe)
# --------------------------------------------------------------------------

def _build_child_map(model: RobotModel) -> Dict[str, List[Joint]]:
    m: Dict[str, List[Joint]] = {}
    for j in model.joints:
        m.setdefault(j.parent, []).append(j)
    return m


def _find_root_links(model: RobotModel) -> List[str]:
    children = {j.child for j in model.joints}
    return [l.name for l in model.links if l.name not in children]


def _kinematic_span_m(model: RobotModel) -> Optional[float]:
    """
    Distance maximale (mètres) entre le lien racine et n'importe quel lien,
    en configuration zéro (tous les joints à 0), transforms d'origine
    appliqués (translation + rotation rpy). Descripteur géométrique
    déterministe -- PAS le workspace réel (qui nécessiterait un
    échantillonnage), mais une borne d'encombrement/allonge exploitable.
    """
    roots = _find_root_links(model)
    if not roots:
        return None
    child_map = _build_child_map(model)
    root = roots[0]
    identity = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    max_d = 0.0
    stack = [(root, (0.0, 0.0, 0.0), identity)]
    seen = set()
    while stack:
        link, pos, rot = stack.pop()
        if link in seen:      # garde-fou anti-cycle
            continue
        seen.add(link)
        d = math.sqrt(sum(c * c for c in pos))
        max_d = max(max_d, d)
        for j in child_map.get(link, []):
            jrot = _rpy_to_matrix(*j.origin_rpy)
            world_rot = _mat_mul(rot, jrot)
            offset = _mat_vec(rot, j.origin_xyz)
            child_pos = tuple(pos[i] + offset[i] for i in range(3))
            stack.append((j.child, child_pos, world_rot))
    return max_d


def derive_capabilities(model: RobotModel) -> dict:
    """Retourne un dict de capacités/chiffres exacts, tous dérivés du URDF."""
    joint_types: Dict[str, int] = {}
    for j in model.joints:
        joint_types[j.type] = joint_types.get(j.type, 0) + 1

    dof = sum(_DOF_BY_TYPE.get(j.type, 0) for j in model.joints)
    actuated = [j for j in model.joints if j.type in _ACTUATED_TYPES]

    masses = [l.mass for l in model.links if l.mass is not None]
    total_mass = round(sum(masses), 4) if masses else None
    links_without_mass = sum(1 for l in model.links if l.mass is None)

    efforts = [j.limit.effort for j in actuated if j.limit and j.limit.effort is not None]
    velocities = [j.limit.velocity for j in actuated if j.limit and j.limit.velocity is not None]
    ranges = [
        round(j.limit.upper - j.limit.lower, 4)
        for j in actuated
        if j.limit and j.limit.lower is not None and j.limit.upper is not None
    ]

    roots = _find_root_links(model)
    children = {j.child for j in model.joints}
    parents = {j.parent for j in model.joints}
    leaves = [l.name for l in model.links if l.name not in parents]

    span = _kinematic_span_m(model)

    return {
        "robot_name": model.name,
        "n_links": len(model.links),
        "n_joints": len(model.joints),
        "joint_types": joint_types,
        "dof": dof,
        "actuated_joint_count": len(actuated),
        "total_mass_kg": total_mass,
        "links_without_mass": links_without_mass,
        "max_joint_effort": round(max(efforts), 4) if efforts else None,
        "max_joint_velocity": round(max(velocities), 4) if velocities else None,
        "sum_actuated_range_rad_or_m": round(sum(ranges), 4) if ranges else None,
        "root_link": roots[0] if roots else None,
        "n_root_links": len(roots),
        "n_leaf_links": len(leaves),
        "kinematic_span_m": round(span, 4) if span is not None else None,
    }


# --------------------------------------------------------------------------
# Squelette de syntaxe nettoyé (pour la branche "syntaxe brute" du corpus)
# --------------------------------------------------------------------------

def make_skeleton(model: RobotModel, max_joints: Optional[int] = None) -> str:
    """
    Régénère un URDF minimal : liens (noms seuls) + joints (type, parent,
    child, axis, origin, limits). SANS <visual>/<collision>/<inertial>/
    meshes. Déterministe, régénéré depuis le modèle (pas un strip regex du
    fichier d'origine), donc aucun chemin de mesh ni commentaire ne fuit.

    max_joints : si fourni, tronque à N joints représentatifs (utile pour
    les robots à très longue chaîne, afin de garder l'extrait compact).
    """
    lines = [f'<robot name="{model.name}">']
    for l in model.links:
        lines.append(f'  <link name="{l.name}"/>')

    joints = model.joints if max_joints is None else model.joints[:max_joints]
    for j in joints:
        lines.append(f'  <joint name="{j.name}" type="{j.type}">')
        lines.append(f'    <parent link="{j.parent}"/>')
        lines.append(f'    <child link="{j.child}"/>')
        ox, oy, oz = j.origin_xyz
        if (ox, oy, oz) != (0.0, 0.0, 0.0):
            lines.append(f'    <origin xyz="{ox:g} {oy:g} {oz:g}"/>')
        if j.axis is not None:
            ax, ay, az = j.axis
            lines.append(f'    <axis xyz="{ax:g} {ay:g} {az:g}"/>')
        if j.limit is not None:
            attrs = []
            for k in ("lower", "upper", "effort", "velocity"):
                v = getattr(j.limit, k)
                if v is not None:
                    attrs.append(f'{k}="{v:g}"')
            if attrs:
                lines.append(f'    <limit {" ".join(attrs)}/>')
        lines.append('  </joint>')

    if max_joints is not None and len(model.joints) > max_joints:
        lines.append(f'  <!-- ... {len(model.joints) - max_joints} joints supplémentaires omis -->')
    lines.append('</robot>')
    return "\n".join(lines)
