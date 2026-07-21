"""
Adaptateurs de la phase 2 -- catégorie 2.

Même patron que cat1 : fichiers -> `DocCandidate` -> (build_corpus) ->
`DocumentDraft` -> enregistrement JSONL. Le nettoyage et le découpage sont
importés de `common/text_clean.py`, partagé avec cat1.

Granularité :

  docs / code   1 fichier = 1 document, découpé si trop long.
  paper         1 article = 1 document, découpé aux frontières de sections.
                Un article de 15 k tokens n'est pas un « document » utile
                en un bloc, et un seul article confisquerait sinon une part
                notable du plafond de la famille.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from common.text_clean import (clean_text_file, collapse_blank_lines,
                               looks_generated, read_text_file, split_document)

# --------------------------------------------------------------------------
# Résidus LaTeX du rendu HTML d'arXiv
#
# Le rendu HTML d'arXiv laisse passer les macros des gabarits d'éditeurs
# (Springer notamment) qu'il ne sait pas interpréter : un article commençait
# par « \equalcont ... [] \fnm Lifeng \sur Zhou \orgdiv Department of... ».
# Ce nettoyage est fait en PHASE 2, pas à la collecte : le fichier récupéré
# doit rester le texte brut extrait, conformément à la séparation des deux
# phases (on peut ainsi améliorer ce filtre sans re-télécharger 43 articles).
# --------------------------------------------------------------------------

_LATEX_MACRO = re.compile(r"\\[a-zA-Z@]+\*?")
_EMPTY_BRACKETS = re.compile(r"(?m)^\s*\[\s*\]\s*")
_LONE_SYMBOL_LINE = re.compile(r"(?m)^\s*[\*∗†‡§¶,;:]+\s*$")


# Début du corps de l'article. Tout ce qui précède est du paratexte
# (auteurs, affiliations, adresses postales, mentions de contribution) :
# aucune valeur pour un corpus de vocabulaire robotique, et cela ferait
# apprendre au modèle des noms propres et des adresses.
_ABSTRACT = re.compile(r"(?im)^\s*(?:\d+\s*)?abstract\b\s*[:.\-—]?\s*$")
_ABSTRACT_INLINE = re.compile(r"(?im)^\s*abstract\b[ \t]*[:.\-—]?[ \t]*\S")
_MAX_FRONTMATTER_CHARS = 4000


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
    # Le bloc d'auteurs répète souvent la même mention, séparée par des
    # lignes vides : on compare donc à la dernière ligne NON vide.
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

MIN_CHARS_DOC = 400
MIN_CHARS_CODE = 300
MIN_CHARS_PAPER = 2000     # un « article » plus court est une extraction ratée

_CODE_EXT = {".py", ".cpp", ".hpp", ".h", ".c", ".cc"}
_DOC_EXT = {".rst", ".md", ".markdown"}


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
        return "(racine)"
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
    """Natures `docs` et `code` : un fichier = un document."""
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
    Nature `paper` : le texte intégral déjà extrait en phase 1.

    Le groupe de diversité est l'identifiant de l'article lui-même : la
    sélection en tourniquet de la phase 2 prélève ainsi une part de CHAQUE
    article avant d'en approfondir un seul. Sans cela, le plafond de la
    famille serait consommé par les cinq premiers articles par ordre
    alphabétique.
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
        raise ValueError(f"nature inconnue : {meta['kind']!r} "
                         f"(connues : {sorted(ADAPTERS)})")
    return adapter(meta, root)
