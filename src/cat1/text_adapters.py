"""
Phase-2 adapters -- category 1.

Each nature of file (`kind`) becomes one or more `DocCandidate`, an
intermediate object local to cat1. Candidates surviving filtering,
deduplication and quotas are converted into `DocumentDraft` (the shared
object) by `build_corpus.py`: the assembler and the output schema stay
untouched, in line with the project's extension principle.

Granularity, per nature:

  docs        1 file = 1 document. A tutorial page is already a unit of
              meaning.
  code        1 file = 1 document.
  interfaces  1 PACKAGE = 1 document. An isolated `.msg` is 30 tokens and
              means nothing out of context; grouped by package they form
              the complete command vocabulary of a domain
              (`geometry_msgs`, `nav2_msgs`...).
  notebooks   1 notebook = 1 document, markdown and code cells only.
              Execution outputs are discarded: they account for most of the
              weight of a .ipynb and carry no usable text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

# Cleaning and splitting: promoted into common/ when cat2 was created,
# since both categories collect the same formats.
from common.text_clean import (clean_md, clean_text_file,
                               collapse_blank_lines, looks_generated,
                               read_text_file, split_document)

# Quality thresholds. A file that is too short is structural noise (index
# page, redirect); it would add volume without content.
MIN_CHARS_DOC = 400
MIN_CHARS_CODE = 300
MIN_CHARS_INTERFACE = 200

_CODE_EXT = {".py", ".cpp", ".hpp", ".h", ".c", ".cc"}
_DOC_EXT = {".rst", ".md", ".markdown"}
_INTERFACE_EXT = {".msg", ".srv", ".action"}


@dataclass
class DocCandidate:
    doc_id: str            # stable identifier, becomes part of the corpus id
    source_id: str
    family: str
    kind: str
    rel_path: str          # path within the source, for traceability
    group: str             # originating subtree, used for diversity
    text: str
    n_tokens: int = 0
    flags: Dict[str, str] = field(default_factory=dict)


def _group_of(rel: Path) -> str:
    """Top-level subtree -- used to spread the selection."""
    parts = rel.parts
    if len(parts) <= 1:
        return "(root)"
    # source/Tutorials/Beginner/... -> go one level deeper when the first
    # level is just a container ("source", "doc", "docs").
    if parts[0] in ("source", "doc", "docs") and len(parts) > 2:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


# --------------------------------------------------------------------------
# Adapters, per nature
# --------------------------------------------------------------------------

def adapt_documents(meta: dict, root: Path) -> List[DocCandidate]:
    """Natures `docs` and `code`: one file = one document."""
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
                continue          # trailing split fragment too thin
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
    Nature `interfaces`: one package = one document.

    Definitions are concatenated with their path as a heading, so the model
    learns the qualified-name -> fields mapping (`nav2_msgs/action/
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
    Nature `notebooks`: markdown and code cells, without the outputs.

    Execution outputs (encoded images, logs) account for most of the weight
    of a .ipynb and carry no useful text; including them would pollute the
    corpus with base64.
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
            flags = {"notebook": "markdown+code cells, outputs discarded"}
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
        raise ValueError(f"unknown nature: {meta['kind']!r} "
                         f"(known: {sorted(ADAPTERS)})")
    return adapter(meta, root)
