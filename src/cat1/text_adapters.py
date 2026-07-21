"""
Adaptateurs de la phase 2 -- catégorie 1.

Chaque nature de fichier (`kind`) devient un ou plusieurs `DocCandidate`,
objet intermédiaire local à cat1. Les candidats retenus après filtrage,
déduplication et quotas sont convertis en `DocumentDraft` (objet commun) par
`build_corpus.py` : l'assembleur et le schéma de sortie restent inchangés,
conformément au principe d'extension du projet.

Granularité choisie, par nature :

  docs        1 fichier = 1 document. Une page de tutoriel est déjà une
              unité de sens.
  code        1 fichier = 1 document.
  interfaces  1 PAQUET = 1 document. Un `.msg` isolé fait 30 tokens et n'a
              aucun sens hors contexte ; regroupés par paquet, ils forment
              le vocabulaire de commande complet d'un domaine
              (`geometry_msgs`, `nav2_msgs`...).
  notebooks   1 notebook = 1 document, cellules markdown + code seulement.
              Les sorties d'exécution sont jetées : elles représentent
              l'essentiel du poids des .ipynb et n'apportent aucun texte
              exploitable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

# Nettoyage et découpage : promus dans common/ lors de la création de cat2,
# cat1 et cat2 collectant les mêmes formats.
from common.text_clean import (clean_md, clean_text_file,
                               collapse_blank_lines, looks_generated,
                               read_text_file, split_document)

# Seuils de qualité. Un fichier trop court est du bruit de structure
# (page d'index, redirection) ; il ferait du volume sans contenu.
MIN_CHARS_DOC = 400
MIN_CHARS_CODE = 300
MIN_CHARS_INTERFACE = 200

_CODE_EXT = {".py", ".cpp", ".hpp", ".h", ".c", ".cc"}
_DOC_EXT = {".rst", ".md", ".markdown"}
_INTERFACE_EXT = {".msg", ".srv", ".action"}



@dataclass
class DocCandidate:
    doc_id: str            # identifiant stable, entre dans l'id du corpus
    source_id: str
    family: str
    kind: str
    rel_path: str          # chemin dans la source, pour la traçabilité
    group: str             # sous-arbre d'origine, utilisé pour la diversité
    text: str
    n_tokens: int = 0
    flags: Dict[str, str] = field(default_factory=dict)



def _group_of(rel: Path) -> str:
    """Sous-arbre de premier niveau -- sert à répartir la sélection."""
    parts = rel.parts
    if len(parts) <= 1:
        return "(racine)"
    # source/Tutorials/Beginner/... -> on descend d'un cran quand le
    # premier niveau est un simple conteneur ("source", "doc", "docs").
    if parts[0] in ("source", "doc", "docs") and len(parts) > 2:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


# --------------------------------------------------------------------------
# Adaptateurs par nature
# --------------------------------------------------------------------------

def adapt_documents(meta: dict, root: Path) -> List[DocCandidate]:
    """Nature `docs` et `code` : un fichier = un document."""
    out: List[DocCandidate] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in _DOC_EXT and ext not in _CODE_EXT:
            continue
        raw = read_text_file(path)
        if raw is None:
            continue
        text = clean_text_file(path, raw)
        min_chars = MIN_CHARS_DOC if ext in _DOC_EXT else MIN_CHARS_CODE
        if len(text) < min_chars or looks_generated(text):
            continue
        rel = path.relative_to(root)
        base_id = str(rel).replace("/", "_").replace(".", "_")
        parts = split_document(text, ext)
        for i, part in enumerate(parts, start=1):
            if len(part) < min_chars:
                continue          # queue de découpage trop maigre
            flags = {}
            suffix = ""
            if len(parts) > 1:
                flags = {"part": str(i), "n_parts": str(len(parts))}
                suffix = f"-p{i}"
            out.append(DocCandidate(
                doc_id=f"{meta['source_id']}-{base_id}{suffix}",
                source_id=meta["source_id"], family=meta["family"],
                kind=meta["kind"], rel_path=str(rel), group=_group_of(rel),
                text=part, flags=flags,
            ))
    return out


def adapt_interfaces(meta: dict, root: Path) -> List[DocCandidate]:
    """
    Nature `interfaces` : un paquet = un document.

    Les définitions sont concaténées avec leur chemin en titre, pour que le
    modèle apprenne le lien nom-qualifié -> champs (`nav2_msgs/action/
    NavigateToPose` -> goal/result/feedback).
    """
    by_package: Dict[str, List[Path]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in _INTERFACE_EXT:
            rel = path.relative_to(root)
            by_package.setdefault(rel.parts[0], []).append(path)

    out: List[DocCandidate] = []
    for package, files in sorted(by_package.items()):
        blocks = [f"# {package} — ROS 2 interface definitions", ""]
        for path in files:
            raw = read_text_file(path)
            if raw is None or not raw.strip():
                continue
            rel = path.relative_to(root)
            kind_dir = rel.parts[1] if len(rel.parts) > 2 else ""
            qualified = f"{package}/{kind_dir}/{path.stem}" if kind_dir else \
                        f"{package}/{path.stem}"
            blocks.append(f"## {qualified} ({path.suffix.lstrip('.')})")
            blocks.append("```")
            blocks.append(raw.strip())
            blocks.append("```")
            blocks.append("")
        text = "\n".join(blocks).strip()
        if len(text) < MIN_CHARS_INTERFACE:
            continue
        out.append(DocCandidate(
            doc_id=f"{meta['source_id']}-{package}",
            source_id=meta["source_id"], family=meta["family"],
            kind=meta["kind"], rel_path=package, group=package,
            text=text, flags={"n_interfaces": str(len(files))},
        ))
    return out


def adapt_notebooks(meta: dict, root: Path) -> List[DocCandidate]:
    """
    Nature `notebooks` : cellules markdown et code, sans les sorties.

    Les sorties d'exécution (images encodées, logs) font l'essentiel du
    poids d'un .ipynb et n'apportent aucun texte utile ; les inclure
    reviendrait à polluer le corpus avec du base64.
    """
    out: List[DocCandidate] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".md":
            raw = read_text_file(path)
            if raw and len(clean_md(raw)) >= MIN_CHARS_DOC:
                rel = path.relative_to(root)
                out.append(DocCandidate(
                    doc_id=f"{meta['source_id']}-{path.stem}",
                    source_id=meta["source_id"], family=meta["family"],
                    kind=meta["kind"], rel_path=str(rel), group=_group_of(rel),
                    text=clean_md(raw),
                ))
            continue
        if path.suffix.lower() != ".ipynb":
            continue

        raw = read_text_file(path)
        if raw is None:
            continue
        try:
            nb = json.loads(raw)
        except json.JSONDecodeError:
            continue

        blocks = [f"# {path.stem}", ""]
        for cell in nb.get("cells", []):
            src = cell.get("source", [])
            body = ("".join(src) if isinstance(src, list) else str(src)).strip()
            if not body:
                continue
            if cell.get("cell_type") == "markdown":
                blocks.append(clean_md(body))
            elif cell.get("cell_type") == "code":
                blocks.append("```python")
                blocks.append(body)
                blocks.append("```")
            blocks.append("")
        text = collapse_blank_lines("\n".join(blocks))
        if len(text) < MIN_CHARS_DOC:
            continue
        rel = path.relative_to(root)
        base_id = path.stem.replace(" ", "_")
        parts = split_document(text, ".md")
        for i, part in enumerate(parts, start=1):
            if len(part) < MIN_CHARS_DOC:
                continue
            flags = {"notebook": "cellules markdown+code, sorties écartées"}
            suffix = ""
            if len(parts) > 1:
                flags.update({"part": str(i), "n_parts": str(len(parts))})
                suffix = f"-p{i}"
            out.append(DocCandidate(
                doc_id=f"{meta['source_id']}-{base_id}{suffix}",
                source_id=meta["source_id"], family=meta["family"],
                kind=meta["kind"], rel_path=str(rel), group=_group_of(rel),
                text=part, flags=flags,
            ))
    return out


ADAPTERS = {
    "docs": adapt_documents,
    "code": adapt_documents,
    "interfaces": adapt_interfaces,
    "notebooks": adapt_notebooks,
}


def adapt(meta: dict, root: Path) -> List[DocCandidate]:
    adapter = ADAPTERS.get(meta["kind"])
    if adapter is None:
        raise ValueError(f"nature inconnue : {meta['kind']!r} "
                         f"(connues : {sorted(ADAPTERS)})")
    return adapter(meta, root)
