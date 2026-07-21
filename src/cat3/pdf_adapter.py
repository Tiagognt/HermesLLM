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
from common.ocr import (OcrUnavailable, looks_like_pdf, ocr_pdf,
                        sniff_file_type)


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


def ocr_cache_path(pdf_path: Path) -> Path:
    """
    Cache OCR, à côté du PDF source. L'OCR coûte quelques secondes par page :
    sans cache, régénérer le corpus (phase 2) relancerait la reconnaissance
    à chaque fois, ce qui reviendrait à coupler les deux phases.
    """
    return pdf_path.parent / f".ocr-{pdf_path.stem}.json"


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
    use_ocr: bool = False,
    ocr_max_pages: Optional[int] = None,
    ocr_progress=None,
) -> DocumentDraft:
    # Contrôle de signature AVANT toute tentative d'extraction : un fichier
    # « .pdf » qui n'en est pas un produisait sinon une erreur pdfminer
    # incompréhensible (« No /Root object! ») n'indiquant aucune action.
    if not looks_like_pdf(pdf_path):
        raise RuntimeError(
            f"{pdf_path.name} n'est pas un PDF : contenu réel détecté = "
            f"{sniff_file_type(pdf_path)}. Le fichier doit être "
            f"re-téléchargé depuis la source officielle."
        )

    pages = _extract_pages_pdfplumber(pdf_path)
    if pages is None:
        pages = [_extract_text_pdftotext(pdf_path)]

    text = clean_text(pages)
    used_ocr = False
    ocr_confidence: Optional[float] = None
    provenance = {"pdf_file": pdf_path.name, "n_pages": len(pages),
                  "extraction": "native"}

    # Un PDF scanné (images seules) ressort quasi vide.
    if len(text) < MIN_USEFUL_CHARS:
        if not use_ocr:
            raise RuntimeError(
                f"{pdf_path.name} : {len(text)} caractères extraits seulement "
                f"({len(pages)} pages) -- PDF probablement scanné ou sans couche "
                f"texte. Relancer avec --ocr, ou écarter ce manuel."
            )
        try:
            result = ocr_pdf(pdf_path, max_pages=ocr_max_pages,
                             cache_path=ocr_cache_path(pdf_path),
                             progress=ocr_progress)
        except OcrUnavailable as exc:
            raise RuntimeError(
                f"{pdf_path.name} : PDF scanné et OCR indisponible. {exc}"
            ) from exc

        text = clean_text([result.text])
        if len(text) < MIN_USEFUL_CHARS:
            raise RuntimeError(
                f"{pdf_path.name} : OCR effectué ({result.describe()}) mais "
                f"seulement {len(text)} caractères exploitables -- document "
                f"à écarter."
            )
        used_ocr = True
        ocr_confidence = result.mean_confidence
        provenance.update({
            "extraction": "ocr",
            "ocr_backend": result.backend,
            "ocr_pages_with_text": result.n_pages_with_text,
            "ocr_mean_confidence": round(result.mean_confidence, 4),
        })

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
        provenance=provenance,
        ocr=used_ocr,
        ocr_confidence=ocr_confidence,
    )
