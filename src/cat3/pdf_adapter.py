"""
Voie PDF de la phase 2 : formatage de manuels/datasheets de robots.

Chaîne : PDF -> extraction texte (pdfplumber, repli pdftotext -layout) ->
nettoyage (en-têtes/pieds de page répétés, numéros de page, césures,
espaces) -> (option) mise en forme LLM strictement EXTRACTIVE ->
DocumentDraft.

IMPORTANT licence : un manuel de fabricant est presque toujours
propriétaire (©), donc HORS de l'allowlist du projet. La licence vient du
manifeste (pdf_manifest.json), est classée par license_utils, et c'est
build_corpus qui décide de l'inclusion via is_collectible. Cet adaptateur
ne force jamais l'inclusion d'un contenu propriétaire.

La mise en forme LLM est DÉSACTIVÉE par défaut : reformuler un manuel via
LLM risque (a) d'inventer des specs, (b) d'aggraver la question de droits.
En extractif pur, le texte reste une extraction fidèle et vérifiable.
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import List, Optional

from common.llm_provider import LLMProvider, TemplateProvider
from common.corpus_assembler import DocumentDraft


# --------------------------------------------------------------------------
# Découverte du fichier PDF
# --------------------------------------------------------------------------

def find_pdf(robot_manual_dir: Path, preferred_name: Optional[str] = None) -> Optional[Path]:
    """
    Trouve le PDF d'un robot dans son dossier de manuels.

    On accepte N'IMPORTE QUEL nom de fichier .pdf : exiger un nom exact
    (l'ancien comportement, "manual.pdf") faisait échouer silencieusement
    tous les manuels réellement téléchargés (g1_manual.pdf, x2_manual.pdf,
    technical_manual.pdf...). preferred_name n'est plus qu'une préférence
    en cas de PDF multiples.
    """
    if not robot_manual_dir.is_dir():
        return None
    pdfs = sorted(p for p in robot_manual_dir.glob("*.pdf") if p.is_file())
    if not pdfs:
        return None
    if preferred_name:
        for p in pdfs:
            if p.name == preferred_name:
                return p
    return pdfs[0]


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

def _extract_pages_pdfplumber(pdf_path: Path) -> Optional[List[str]]:
    try:
        import pdfplumber
    except ImportError:
        return None      # pdfplumber non installé -> repli pdftotext
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for p in pdf.pages:
            pages.append(p.extract_text() or "")
    return pages


def _extract_text_pdftotext(pdf_path: Path) -> str:
    # Repli : poppler, en préservant la mise en page (utile multi-colonnes).
    out = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"pdftotext a échoué sur {pdf_path}: {out.stderr[:200]}")
    return out.stdout


# --------------------------------------------------------------------------
# Nettoyage
# --------------------------------------------------------------------------

_PAGE_NUM_RE = re.compile(r"^\s*(page\s*)?\d+\s*(/\s*\d+)?\s*$", re.IGNORECASE)


def _strip_repeated_headers_footers(pages: List[str], min_fraction: float = 0.5) -> List[str]:
    """Supprime les lignes (en-têtes/pieds) qui réapparaissent sur >= min_fraction des pages."""
    if len(pages) < 4:
        return pages
    first_last = Counter()
    for pg in pages:
        lines = [l.strip() for l in pg.splitlines() if l.strip()]
        for l in lines[:2] + lines[-2:]:
            first_last[l] += 1
    threshold = max(2, int(min_fraction * len(pages)))
    boilerplate = {l for l, c in first_last.items() if c >= threshold}
    cleaned = []
    for pg in pages:
        kept = [l for l in pg.splitlines() if l.strip() not in boilerplate]
        cleaned.append("\n".join(kept))
    return cleaned


def clean_text(pages: List[str]) -> str:
    pages = _strip_repeated_headers_footers(pages)
    lines: List[str] = []
    for pg in pages:
        for raw in pg.splitlines():
            line = raw.rstrip()
            if _PAGE_NUM_RE.match(line):      # ligne = numéro de page seul
                continue
            lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)      # dé-césure fin de ligne
    text = re.sub(r"[ \t]+", " ", text)               # espaces multiples
    text = re.sub(r"\n{3,}", "\n\n", text)            # lignes vides multiples
    return text.strip()


# --------------------------------------------------------------------------
# Mise en forme LLM (optionnelle, strictement extractive)
# --------------------------------------------------------------------------

_FORMAT_SYSTEM = (
    "You reformat robot manual excerpts into clean plain text. Preserve every "
    "fact and number exactly. Remove page furniture and fix line breaks. "
    "NEVER add, infer, or 'correct' any specification, number, or unit."
)


def llm_format(text: str, provider: LLMProvider, max_chars: int = 12000) -> str:
    if isinstance(provider, TemplateProvider):
        return text  # pas de LLM configuré -> extractif pur
    prompt = ("Reformat the following robot manual excerpt. Keep all facts and "
              "numbers verbatim.\n\n" + text[:max_chars])
    return provider.generate(prompt, system=_FORMAT_SYSTEM).strip()


# --------------------------------------------------------------------------
# Adaptateur
# --------------------------------------------------------------------------

MIN_USEFUL_CHARS = 200   # en dessous : PDF probablement scanné (pas de couche texte)


def adapt(
    robot_id: str,
    pdf_path: Path,
    *,
    license_status: str,
    url: str = "",
    source_name: str = "",
    provider: Optional[LLMProvider] = None,
    use_llm_format: bool = False,
    max_chars: Optional[int] = 40000,
) -> DocumentDraft:
    pages = _extract_pages_pdfplumber(pdf_path)
    if pages is None:
        pages = [_extract_text_pdftotext(pdf_path)]

    text = clean_text(pages)

    # Un PDF scanné (images seules) ressort quasi vide : mieux vaut une
    # erreur explicite qu'un enregistrement vide dans le corpus.
    if len(text) < MIN_USEFUL_CHARS:
        raise RuntimeError(
            f"{pdf_path.name} : {len(text)} caractères extraits seulement "
            f"({len(pages)} pages) -- PDF probablement scanné ou sans couche "
            f"texte. OCR nécessaire, ou écarter ce manuel."
        )

    if use_llm_format and provider is not None:
        text = llm_format(text, provider)
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n[... tronqué ...]"

    return DocumentDraft(
        robot_id=robot_id,
        source_type="pdf_manual",
        text=text,
        license_status=license_status,
        url=url,
        lang="en",
        source_name=source_name or f"manual:{robot_id}",
        provenance={"pdf_file": pdf_path.name, "n_pages": len(pages)},
    )
