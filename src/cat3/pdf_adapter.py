"""
PDF path of phase 2: formatting robot manuals and datasheets.

Chain: PDF -> text extraction (pdfplumber, pdftotext -layout fallback) ->
cleaning (repeated headers/footers, page numbers, hyphenation, spacing) ->
(optional) strictly EXTRACTIVE LLM formatting -> DocumentDraft.

LICENSE, important: a vendor manual is almost always proprietary (c), hence
OUTSIDE the project allowlist. The license comes from the manifest
(pdf_manifest.json), is classified by license_utils, and it is build_corpus
that decides on inclusion through is_collectible. This adapter never forces
the inclusion of proprietary content.

LLM formatting is DISABLED by default: rephrasing a manual through an LLM
risks (a) inventing specifications and (b) worsening the rights question.
In purely extractive mode the text stays a faithful, verifiable extraction.
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
# Finding the PDF file
# --------------------------------------------------------------------------

def find_pdf(robot_manual_dir: Path, preferred_name: Optional[str] = None) -> Optional[Path]:
    """
    Find a robot's PDF inside its manual directory.

    ANY .pdf filename is accepted: requiring an exact name (the old
    behaviour, "manual.pdf") silently failed for every manual actually
    downloaded (g1_manual.pdf, x2_manual.pdf, technical_manual.pdf...).
    preferred_name is now only a preference when several PDFs are present.
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
        return None      # pdfplumber not installed -> pdftotext fallback
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for p in pdf.pages:
            pages.append(p.extract_text() or "")
    return pages


def _extract_text_pdftotext(pdf_path: Path) -> str:
    # Fallback: poppler, preserving layout (useful for multi-column pages).
    out = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"pdftotext failed on {pdf_path}: {out.stderr[:200]}")
    return out.stdout


# --------------------------------------------------------------------------
# Cleaning
# --------------------------------------------------------------------------

_PAGE_NUM_RE = re.compile(r"^\s*(page\s*)?\d+\s*(/\s*\d+)?\s*$", re.IGNORECASE)


def _strip_repeated_headers_footers(pages: List[str], min_fraction: float = 0.5) -> List[str]:
    """Remove lines (headers/footers) recurring on >= min_fraction of pages."""
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
            if _PAGE_NUM_RE.match(line):      # line is just a page number
                continue
            lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)      # de-hyphenate line ends
    text = re.sub(r"[ \t]+", " ", text)               # multiple spaces
    text = re.sub(r"\n{3,}", "\n\n", text)            # multiple blank lines
    return text.strip()


# --------------------------------------------------------------------------
# LLM formatting (optional, strictly extractive)
# --------------------------------------------------------------------------

_FORMAT_SYSTEM = (
    "You reformat robot manual excerpts into clean plain text. Preserve every "
    "fact and number exactly. Remove page furniture and fix line breaks. "
    "NEVER add, infer, or 'correct' any specification, number, or unit."
)


def llm_format(text: str, provider: LLMProvider, max_chars: int = 12000) -> str:
    if isinstance(provider, TemplateProvider):
        return text  # no LLM configured -> purely extractive
    prompt = ("Reformat the following robot manual excerpt. Keep all facts and "
              "numbers verbatim.\n\n" + text[:max_chars])
    return provider.generate(prompt, system=_FORMAT_SYSTEM).strip()


# --------------------------------------------------------------------------
# Adapter
# --------------------------------------------------------------------------

MIN_USEFUL_CHARS = 200   # below this: probably a scanned PDF (no text layer)


def ocr_cache_path(pdf_path: Path) -> Path:
    """
    OCR cache, next to the source PDF. OCR costs a few seconds per page:
    without a cache, regenerating the corpus (phase 2) would re-run
    recognition every time, which would amount to coupling the two phases.
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
    # Signature check BEFORE any extraction attempt: a ".pdf" file that is
    # not one used to produce an incomprehensible pdfminer error
    # ("No /Root object!") pointing at no action at all.
    if not looks_like_pdf(pdf_path):
        raise RuntimeError(
            f"{pdf_path.name} is not a PDF: real content detected = "
            f"{sniff_file_type(pdf_path)}. The file must be re-downloaded "
            f"from its official source."
        )

    pages = _extract_pages_pdfplumber(pdf_path)
    if pages is None:
        pages = [_extract_text_pdftotext(pdf_path)]

    text = clean_text(pages)
    used_ocr = False
    ocr_confidence: Optional[float] = None
    provenance = {"pdf_file": pdf_path.name, "n_pages": len(pages),
                  "extraction": "native"}

    # A scanned PDF (images only) comes out nearly empty.
    if len(text) < MIN_USEFUL_CHARS:
        if not use_ocr:
            raise RuntimeError(
                f"{pdf_path.name}: only {len(text)} characters extracted "
                f"({len(pages)} pages) -- probably a scanned PDF or one with "
                f"no text layer. Re-run with --ocr, or drop this manual."
            )
        try:
            result = ocr_pdf(pdf_path, max_pages=ocr_max_pages,
                             cache_path=ocr_cache_path(pdf_path),
                             progress=ocr_progress)
        except OcrUnavailable as exc:
            raise RuntimeError(
                f"{pdf_path.name}: scanned PDF and OCR unavailable. {exc}"
            ) from exc

        text = clean_text([result.text])
        if len(text) < MIN_USEFUL_CHARS:
            raise RuntimeError(
                f"{pdf_path.name}: OCR performed ({result.describe()}) but "
                f"only {len(text)} usable characters -- document to drop."
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
        text = text[:max_chars].rstrip() + "\n[... truncated ...]"

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
