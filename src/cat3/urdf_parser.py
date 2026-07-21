"""
Deterministic parsing of a URDF into a robot-agnostic intermediate
representation, THEN derivation of capabilities (DOF, mass, limits,
kinematic reach) and extraction of a cleaned syntax skeleton.

Key principle of the project: EVERY number in the final corpus comes from
here, from code, never from an LLM. The natural-language description
(separate LLM module) only rephrases values already extracted here -- and a
guardrail verifies that it invents no number.

No ROS dependency. Hand-rolled 3D maths (no external dependency beyond the
standard library) so it stays installable anywhere.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Degrees of freedom per URDF joint type.
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
# Intermediate representation
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
    mass: Optional[float] = None   # None when there is no <inertial><mass>


@dataclass
class RobotModel:
    name: str
    links: List[Link] = field(default_factory=list)
    joints: List[Joint] = field(default_factory=list)
    # Repairs applied to the XML before parsing. Never silent: the caller
    # logs them (rule "no silent skip").
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
# XML reading tolerant of undeclared namespace prefixes
#
# Some URDFs published in the Gazebo Classic era contain prefixed tags
# (<sensor:camera>, <controller:gazebo_ros_camera>) without the matching
# xmlns:. That is invalid XML: ElementTree rejects the entire file with
# "unbound prefix", so we used to lose the WHOLE robot (real case: fetch,
# line 655) even though its <link>/<joint> elements are perfectly fine.
#
# We therefore declare the missing prefixes on the root element before
# parsing. No data is removed or rewritten: we only add the absent xmlns
# declarations. The affected elements end up in a dummy namespace and are
# thus ignored by our unprefixed findall("link")/findall("joint") -- exactly
# the desired behaviour, since they are simulator extensions, not kinematic
# description.
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
        raise ET.ParseError("no root element found in the document")
    decls = " " + " ".join(
        f'xmlns:{p}="{_UNDECLARED_NS_FMT.format(p)}"' for p in prefixes)
    insert_at = m.end(1)
    return raw[:insert_at] + decls + raw[insert_at:]


def read_urdf_xml(path: Path) -> Tuple[ET.Element, List[str]]:
    """
    Returns (root, notes). `notes` documents any repair applied. An XML
    error that is not an undeclared prefix is re-raised unchanged: we only
    repair what we can repair without inventing anything.
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
        note = (f"XML repaired before parsing: undeclared namespace "
                f"prefix(es) {prefixes} (original error: {first_error}). "
                f"xmlns declarations added on the root; the affected "
                f"elements (simulator extensions) are ignored.")
        return root, [note]


def parse_urdf(path: Path) -> RobotModel:
    """Read a URDF file and return a RobotModel. Robust to missing fields."""
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
# Small 3D algebra (numpy not required)
# --------------------------------------------------------------------------

def _rpy_to_matrix(r: float, p: float, y: float) -> List[List[float]]:
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    # R = Rz(y) @ Ry(p) @ Rx(r)  (URDF convention)
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
# Capability derivation (deterministic)
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
    Maximum distance (metres) between the root link and any link, in the
    zero configuration (all joints at 0), with the origin transforms
    applied (translation + rpy rotation). A deterministic geometric
    descriptor -- NOT the real workspace (which would require sampling),
    but a usable bound on extent/reach.
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
        if link in seen:      # anti-cycle guard
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
    """Return a dict of exact capabilities/figures, all derived from the URDF."""
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
# Cleaned syntax skeleton (for the "raw syntax" branch of the corpus)
# --------------------------------------------------------------------------

def make_skeleton(model: RobotModel, max_joints: Optional[int] = None) -> str:
    """
    Regenerate a minimal URDF: links (names only) plus joints (type, parent,
    child, axis, origin, limits). WITHOUT <visual>/<collision>/<inertial>/
    meshes. Deterministic, regenerated from the model (not a regex strip of
    the original file), so no mesh path or comment can leak.

    max_joints: when given, truncate to N representative joints (useful for
    robots with very long chains, to keep the excerpt compact).
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
        lines.append(f'  <!-- ... {len(model.joints) - max_joints} additional joints omitted -->')
    lines.append('</robot>')
    return "\n".join(lines)
