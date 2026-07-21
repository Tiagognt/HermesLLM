"""
Phase-2 adapters -- category 2.

Same pattern as cat1: files -> `DocCandidate` -> (build_corpus) ->
`DocumentDraft` -> JSONL record. Cleaning and splitting are imported from
`common/text_clean.py`, shared with cat1.

Granularity:

  docs / code   1 file = 1 document, split if too long.
  paper         1 paper = 1 document, split at section boundaries. A
                15k-token paper is not a useful "document" in one block,
                and a single paper would otherwise confiscate a noticeable
                share of the family cap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from common.text_clean import (clean_text_file, collapse_blank_lines,
                               looks_generated, read_text_file, split_document)

# --------------------------------------------------------------------------
# LaTeX residue left by the arXiv HTML rendering
#
# The arXiv HTML renderer lets through the macros of publisher templates
# (Springer in particular) that it cannot interpret: one paper started with
# "\equalcont ... [] \fnm Lifeng \sur Zhou \orgdiv Department of...".
# This cleaning happens in PHASE 2, not at collection time: the fetched
# file must stay the raw extracted text, in line with the separation of the
# two phases (the filter can thus be improved without re-downloading 43
# papers).
# --------------------------------------------------------------------------

_LATEX_MACRO = re.compile(r"\\[a-zA-Z@]+\*?")
_EMPTY_BRACKETS = re.compile(r"(?m)^\s*\[\s*\]\s*")
_LONE_SYMBOL_LINE = re.compile(r"(?m)^\s*[\*∗†‡§¶,;:]+\s*$")

# Start of the paper body. Everything before it is front matter (authors,
# affiliations, postal addresses, contribution statements): no value for a
# robotics vocabulary corpus, and it would teach the model proper names and
# street addresses.
_ABSTRACT = re.compile(r"(?im)^\s*(?:\d+\s*)?abstract\b\s*[:.\-—]?\s*$")
_ABSTRACT_INLINE = re.compile(r"(?im)^\s*abstract\b[ \t]*[:.\-—]?[ \t]*\S")
_MAX_FRONTMATTER_CHARS = 4000

MIN_CHARS_DOC = 400
MIN_CHARS_CODE = 300
MIN_CHARS_PAPER = 2000     # a shorter "paper" means a failed extraction

_CODE_EXT = {".py", ".cpp", ".hpp", ".h", ".c", ".cc"}
_DOC_EXT = {".rst", ".md", ".markdown"}


def _drop_frontmatter(text: str) -> str:
    for pattern in (_ABSTRACT, _ABSTRACT_INLINE):
        m = pattern.search(text[:_MAX_FRONTMATTER_CHARS])
        if m:
            return text[m.start():]
    return text


def strip_latex_artifacts(text: str) -> str:
    text = _LATEX_MACRO.sub(" ", text)
    text = _EMPTY_BRACKETS.sub("", text)
    text = _LONE_SYMBOL_LINE.sub("", text)
    text = _drop_frontmatter(text)
    # The author block often repeats the same statement, separated by blank
    # lines: we therefore compare against the last NON-empty line.
    out: List[str] = []
    previous = None
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and stripped == previous:
            continue
        out.append(line)
        if stripped:
            previous = stripped
    text = "\n".join(out)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return collapse_blank_lines(text)


@dataclass
class DocCandidate:
    doc_id: str
    source_id: str
    family: str
    kind: str
    rel_path: str
    group: str
    text: str
    n_tokens: int = 0
    flags: Dict[str, str] = field(default_factory=dict)


def _group_of(rel: Path) -> str:
    parts = rel.parts
    if len(parts) <= 1:
        return "(root)"
    if parts[0] in ("src", "doc", "docs") and len(parts) > 2:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


def _emit(meta: dict, base_id: str, rel: str, group: str, parts: List[str],
          min_chars: int, extra_flags: Dict[str, str]) -> List[DocCandidate]:
    out: List[DocCandidate] = []
    for i, part in enumerate(parts, start=1):
        if len(part) < min_chars:
            continue
        flags = dict(extra_flags)
        suffix = ""
        if len(parts) > 1:
            flags.update({"part": str(i), "n_parts": str(len(parts))})
            suffix = f"-p{i}"
        out.append(DocCandidate(
            doc_id=f"{meta['source_id']}-{base_id}{suffix}",
            source_id=meta["source_id"], family=meta["family"],
            kind=meta["kind"], rel_path=rel, group=group,
            text=part, flags=flags,
        ))
    return out


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
        out.extend(_emit(meta, base_id, str(rel), _group_of(rel),
                         split_document(text, ext), min_chars, {}))
    return out


def adapt_paper(meta: dict, root: Path) -> List[DocCandidate]:
    """
    Nature `paper`: the full text already extracted in phase 1.

    The diversity group is the paper identifier itself, so the phase-2
    round-robin selection takes a slice of EVERY paper before going deeper
    into any single one. Without that, the family cap would be consumed by
    the first five papers in alphabetical order.
    """
    path = root / "paper.txt"
    if not path.is_file():
        return []
    text = strip_latex_artifacts((read_text_file(path) or "").strip())
    if len(text) < MIN_CHARS_PAPER:
        return []
    arxiv_id = meta["repo_commit"]
    return _emit(meta, arxiv_id, "paper.txt", f"arxiv:{arxiv_id}",
                 split_document(text, ".md"), MIN_CHARS_PAPER,
                 {"arxiv_id": arxiv_id, "fetch": meta.get("repo_ref", "")})


ADAPTERS = {
    "docs": adapt_documents,
    "code": adapt_documents,
    "paper": adapt_paper,
}


def adapt(meta: dict, root: Path) -> List[DocCandidate]:
    adapter = ADAPTERS.get(meta["kind"])
    if adapter is None:
        raise ValueError(f"unknown nature: {meta['kind']!r} "
                         f"(known: {sorted(ADAPTERS)})")
    return adapter(meta, root)
