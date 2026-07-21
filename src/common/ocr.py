"""
OCR for PDFs with no text layer -- shared by cat1 / cat2 / cat3.

Context: two of the category-3 manuals are *scanned* PDFs (images only).
pdfplumber/pdftotext extract 0 characters from them, and pdf_adapter then
raises an explicit error rather than writing an empty record. This module
provides the fallback: rasterise, then recognise the text.

Engine chain, tried in order:

  1. rapidocr-onnxruntime -- installable with pip alone (ONNX models
     bundled), no system dependency. It is the engine retained here because
     installing tesseract requires root privileges, unavailable on this
     machine.
  2. tesseract (via pytesseract, or the binary as a fallback) -- if it is
     ever installed it is preferred for purely Latin script.

Rasterisation goes through `pdftoppm` (poppler-utils), already required by
the project as a text-extraction fallback.

IMPORTANT WARNING, read before using the result
------------------------------------------------
OCR is fallible on DIGITS ("V1.0" read as "V1.o", "0.5" as "O.5"), and rule
number one of the project is that no number in the corpus may be doubtful.
The text produced here is therefore NOT of the same quality as a native
extraction:

  - every OCR'd document is marked `ocr: true` in the corpus, with its mean
    confidence, so it stays filterable downstream;
  - blocks below the confidence threshold are dropped, not guessed;
  - recognised text is never "corrected": no heuristic post-processing that
    would invent characters.

Usage:

    from common.ocr import ocr_pdf
    result = ocr_pdf(path, cache_path=path.parent / ".ocr_cache.json")
    result.text, result.mean_confidence, result.backend
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

DEFAULT_DPI = 200
DEFAULT_MIN_CONFIDENCE = 0.5

# Cache format version: incrementing it invalidates existing caches (do so
# if the OCR chain changes in a way that would change the produced text).
CACHE_VERSION = 2

# Rasterisation bounds. Some "manuals" are in fact a single endless page (a
# scrolling Chinese product page): the G1 manual is 20 x 784 inches, i.e.
# 627 Mpx at 200 dpi -- enough to trip the image decoder's
# decompression-bomb guard and, even without that, enough for the OCR
# engine to downscale the image into illegibility. We therefore bound the
# width, then cut the height into bands.
MAX_RASTER_WIDTH_PX = 2000     # beyond this the engine downscales by itself
MAX_BAND_HEIGHT_PX = 1600      # height of one band sent to the OCR engine
BAND_OVERLAP_PX = 120          # overlap, so a line is never cut in half


class OcrUnavailable(RuntimeError):
    """No usable OCR engine in this environment."""


@dataclass
class OcrResult:
    text: str
    backend: str
    n_pages: int
    n_pages_with_text: int
    mean_confidence: float
    page_confidences: List[float] = field(default_factory=list)
    from_cache: bool = False

    def describe(self) -> str:
        return (f"OCR {self.backend}: {self.n_pages_with_text}/{self.n_pages} "
                f"pages with text, mean confidence "
                f"{self.mean_confidence:.2f}, {len(self.text)} characters"
                f"{' (cache)' if self.from_cache else ''}")


# --------------------------------------------------------------------------
# Guardrail: is this even a PDF?
# --------------------------------------------------------------------------

def looks_like_pdf(path: Path) -> bool:
    """
    Check the %PDF- signature at the head of the file.

    Real case encountered: a "manual.pdf" that was in fact an HTML page
    saved by a browser. Without this check the reported error is pdfminer's
    opaque "No /Root object!", which points at no action at all. Here we
    can say what to do: re-download the file.
    """
    try:
        with path.open("rb") as f:
            return f.read(5) == b"%PDF-"
    except OSError:
        return False


def sniff_file_type(path: Path) -> str:
    """Short description of the real content, for a useful error message."""
    try:
        with path.open("rb") as f:
            head = f.read(1024)
    except OSError as exc:
        return f"unreadable ({exc})"
    if head.startswith(b"%PDF-"):
        return "PDF"
    lowered = head.lstrip().lower()
    if lowered.startswith(b"<!doctype html") or lowered.startswith(b"<html"):
        return "HTML"
    if head.startswith(b"PK\x03\x04"):
        return "ZIP archive (docx/xlsx?)"
    if head.startswith(b"\x89PNG"):
        return "PNG image"
    if head.startswith(b"\xff\xd8\xff"):
        return "JPEG image"
    return "unknown"


# --------------------------------------------------------------------------
# Rasterisation
# --------------------------------------------------------------------------

def _pdfinfo(pdf_path: Path, *args: str) -> str:
    proc = subprocess.run(["pdfinfo", *args, str(pdf_path)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"pdfinfo failed on {pdf_path.name}: {proc.stderr.strip()[:200]}")
    return proc.stdout


def count_pdf_pages(pdf_path: Path) -> int:
    m = re.search(r"^Pages:\s+(\d+)", _pdfinfo(pdf_path), re.MULTILINE)
    if not m:
        raise RuntimeError(f"Page count not found for {pdf_path.name}")
    return int(m.group(1))


def page_size_pts(pdf_path: Path, page: int) -> Tuple[float, float]:
    out = _pdfinfo(pdf_path, "-f", str(page), "-l", str(page))
    m = re.search(r"Page(?:\s+\d+)?\s+size:\s+([\d.]+) x ([\d.]+) pts", out)
    if not m:
        raise RuntimeError(f"Page size not found for {pdf_path.name} p{page}")
    return float(m.group(1)), float(m.group(2))


@dataclass
class _Band:
    """A horizontal band of a page, in pixels at the chosen resolution."""
    y: int
    height: int


def plan_page_render(pdf_path: Path, page: int, dpi: int) -> Tuple[int, int, int, List[_Band]]:
    """
    Returns (effective_dpi, width_px, height_px, bands).

    The dpi is lowered if needed so the width stays under
    MAX_RASTER_WIDTH_PX, then the height is cut into overlapping bands. A
    normal page yields a single band covering the whole page: the nominal
    path is unchanged.
    """
    w_pts, h_pts = page_size_pts(pdf_path, page)
    eff_dpi = dpi
    if w_pts > 0:
        max_dpi_for_width = int(MAX_RASTER_WIDTH_PX * 72.0 / w_pts)
        eff_dpi = max(36, min(dpi, max_dpi_for_width))

    width_px = max(1, int(w_pts / 72.0 * eff_dpi))
    height_px = max(1, int(h_pts / 72.0 * eff_dpi))

    if height_px <= MAX_BAND_HEIGHT_PX:
        return eff_dpi, width_px, height_px, [_Band(0, height_px)]

    bands: List[_Band] = []
    step = MAX_BAND_HEIGHT_PX - BAND_OVERLAP_PX
    y = 0
    while y < height_px:
        h = min(MAX_BAND_HEIGHT_PX, height_px - y)
        bands.append(_Band(y, h))
        if y + h >= height_px:
            break
        y += step
    return eff_dpi, width_px, height_px, bands


def _render_band(pdf_path: Path, page: int, out_dir: Path, dpi: int,
                 width_px: int, band: _Band, index: int) -> Optional[Path]:
    prefix = out_dir / f"p{page:05d}b{index:05d}"
    cmd = ["pdftoppm", "-r", str(dpi), "-png",
           "-f", str(page), "-l", str(page),
           "-x", "0", "-y", str(band.y),
           "-W", str(width_px), "-H", str(band.height),
           str(pdf_path), str(prefix)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"pdftoppm failed on {pdf_path.name} page {page} "
            f"band {index}: {proc.stderr.strip()[:200]}"
        )
    produced = sorted(out_dir.glob(f"p{page:05d}b{index:05d}*.png"))
    return produced[0] if produced else None


def _merge_bands(texts: List[str]) -> str:
    """
    Re-join the bands, dropping lines duplicated by the overlap. Only a line
    strictly identical to a recent one is removed: no reconstruction, no
    correction.
    """
    merged: List[str] = []
    for text in texts:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if merged and stripped == merged[-1]:
                continue
            # The overlap can bring back several lines just seen: look at a
            # short backward window.
            if stripped in merged[-4:]:
                continue
            merged.append(stripped)
    return "\n".join(merged)


# --------------------------------------------------------------------------
# Engines
# --------------------------------------------------------------------------

class _Backend:
    name = "base"

    def available(self) -> bool:
        raise NotImplementedError

    def read_image(self, image: Path, min_confidence: float) -> tuple:
        """Returns (page_text, mean_confidence)."""
        raise NotImplementedError


class _RapidOcrBackend(_Backend):
    name = "rapidocr-onnxruntime"

    def __init__(self):
        self._engine = None

    def available(self) -> bool:
        try:
            import rapidocr_onnxruntime  # noqa: F401
            return True
        except ImportError:
            return False

    def _get_engine(self):
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR()
        return self._engine

    def read_image(self, image: Path, min_confidence: float) -> tuple:
        engine = self._get_engine()
        res, _elapse = engine(str(image))
        if not res:
            return "", 0.0

        # res: [[box, text, score], ...]. Group by line (y centre) then
        # order left to right: reading order is not guaranteed by the
        # detector.
        items = []
        for box, text, score in res:
            if score < min_confidence:
                continue          # doubtful block: dropped, never guessed
            ys = [p[1] for p in box]
            xs = [p[0] for p in box]
            items.append(((min(ys) + max(ys)) / 2.0, min(xs), text, score))
        if not items:
            return "", 0.0

        heights = [abs(max(p[1] for p in box) - min(p[1] for p in box))
                   for box, _t, _s in res]
        line_tol = max(8.0, (sum(heights) / len(heights)) * 0.6)

        items.sort(key=lambda it: (it[0], it[1]))
        lines: List[List[tuple]] = []
        for it in items:
            if lines and abs(it[0] - lines[-1][0][0]) <= line_tol:
                lines[-1].append(it)
            else:
                lines.append([it])

        out_lines = []
        for line in lines:
            line.sort(key=lambda it: it[1])
            out_lines.append(" ".join(it[2] for it in line))
        scores = [it[3] for it in items]
        return "\n".join(out_lines), sum(scores) / len(scores)


class _TesseractBackend(_Backend):
    name = "tesseract"

    def available(self) -> bool:
        if shutil.which("tesseract") is None:
            return False
        try:
            import pytesseract  # noqa: F401
            return True
        except ImportError:
            return True   # we know how to drive the binary directly

    def read_image(self, image: Path, min_confidence: float) -> tuple:
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            proc = subprocess.run(["tesseract", str(image), "stdout"],
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"tesseract failed: {proc.stderr[:200]}")
            # Binary mode reports no usable confidence.
            return proc.stdout, 1.0 if proc.stdout.strip() else 0.0

        data = pytesseract.image_to_data(
            Image.open(image), output_type=pytesseract.Output.DICT)
        words, scores = [], []
        for text, conf in zip(data["text"], data["conf"]):
            try:
                c = float(conf) / 100.0
            except (TypeError, ValueError):
                continue
            if text.strip() and c >= min_confidence:
                words.append(text)
                scores.append(c)
        if not words:
            return "", 0.0
        return " ".join(words), sum(scores) / len(scores)


def _select_backend(preferred: Optional[str] = None) -> _Backend:
    backends = [_TesseractBackend(), _RapidOcrBackend()]
    if preferred:
        for b in backends:
            if b.name.startswith(preferred):
                if not b.available():
                    raise OcrUnavailable(
                        f"Requested OCR engine unavailable: {preferred}")
                return b
        raise OcrUnavailable(
            f"Unknown OCR engine: {preferred} "
            f"(known: {[b.name for b in backends]})")
    for b in backends:
        if b.available():
            return b
    raise OcrUnavailable(
        "No OCR engine available. Install either:\n"
        "  pip install rapidocr-onnxruntime      (no root required)\n"
        "  sudo apt-get install tesseract-ocr && pip install pytesseract"
    )


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------

def _source_signature(pdf_path: Path) -> dict:
    st = pdf_path.stat()
    return {"name": pdf_path.name, "size": st.st_size}


def _load_cache(cache_path: Path, pdf_path: Path, params: dict) -> Optional[OcrResult]:
    if not cache_path.exists():
        return None
    try:
        blob = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if blob.get("cache_version") != CACHE_VERSION:
        return None
    if blob.get("source") != _source_signature(pdf_path):
        return None      # the PDF changed -> stale cache
    if blob.get("params") != params:
        return None      # different dpi / threshold / engine -> redo
    return OcrResult(
        text=blob["text"],
        backend=blob["backend"],
        n_pages=blob["n_pages"],
        n_pages_with_text=blob["n_pages_with_text"],
        mean_confidence=blob["mean_confidence"],
        page_confidences=blob.get("page_confidences", []),
        from_cache=True,
    )


def _store_cache(cache_path: Path, pdf_path: Path, params: dict,
                 result: OcrResult) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({
        "cache_version": CACHE_VERSION,
        "source": _source_signature(pdf_path),
        "params": params,
        "backend": result.backend,
        "n_pages": result.n_pages,
        "n_pages_with_text": result.n_pages_with_text,
        "mean_confidence": result.mean_confidence,
        "page_confidences": result.page_confidences,
        "text": result.text,
    }, ensure_ascii=False, indent=1), encoding="utf-8")


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------

def ocr_pdf(
    pdf_path: Path,
    *,
    dpi: int = DEFAULT_DPI,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    max_pages: Optional[int] = None,
    backend: Optional[str] = None,
    cache_path: Optional[Path] = None,
    progress=None,
) -> OcrResult:
    """
    Run OCR on a PDF page by page and return the recognised text.

    max_pages: bounds the cost (OCR runs at a few seconds per page on CPU).
    If the PDF is longer, the remaining pages are skipped -- and the fact is
    reported in the produced text, never silently dropped.
    cache_path: when supplied, the result is read from / written to that
    file, so regenerating the corpus never re-runs OCR (the two phases stay
    independent).
    """
    if not looks_like_pdf(pdf_path):
        raise RuntimeError(
            f"{pdf_path.name} is not a PDF (detected content: "
            f"{sniff_file_type(pdf_path)}). The file must be re-downloaded "
            f"from its source."
        )

    params = {"dpi": dpi, "min_confidence": min_confidence,
              "max_pages": max_pages, "backend": backend}
    if cache_path is not None:
        cached = _load_cache(cache_path, pdf_path, params)
        if cached is not None:
            return cached

    engine = _select_backend(backend)
    total_pages = count_pdf_pages(pdf_path)
    n_pages = min(total_pages, max_pages) if max_pages else total_pages

    page_texts: List[str] = []
    page_confs: List[float] = []
    with tempfile.TemporaryDirectory(prefix="hermes-ocr-") as tmp:
        tmp_dir = Path(tmp)
        for page in range(1, n_pages + 1):
            eff_dpi, width_px, _height_px, bands = plan_page_render(
                pdf_path, page, dpi)
            band_texts: List[str] = []
            band_confs: List[float] = []
            for i, band in enumerate(bands):
                image = _render_band(pdf_path, page, tmp_dir, eff_dpi,
                                     width_px, band, i)
                if image is None:
                    continue
                text, conf = engine.read_image(image, min_confidence)
                image.unlink(missing_ok=True)
                if text.strip():
                    band_texts.append(text)
                    band_confs.append(conf)
                if progress is not None and len(bands) > 1:
                    progress(page, n_pages, conf,
                             {"band": i + 1, "bands": len(bands),
                              "dpi": eff_dpi})
            page_conf = (sum(band_confs) / len(band_confs)) if band_confs else 0.0
            page_texts.append(_merge_bands(band_texts))
            page_confs.append(page_conf)
            if progress is not None and len(bands) == 1:
                progress(page, n_pages, page_conf, {"dpi": eff_dpi})

    kept = [(t, c) for t, c in zip(page_texts, page_confs) if t.strip()]
    body = "\n\n".join(t.strip() for t, _ in kept)
    if max_pages and total_pages > n_pages:
        body += (f"\n\n[... {total_pages - n_pages} pages not OCR'd "
                 f"(max_pages={max_pages} limit) ...]")

    result = OcrResult(
        text=body,
        backend=engine.name,
        n_pages=total_pages,
        n_pages_with_text=len(kept),
        mean_confidence=(sum(c for _, c in kept) / len(kept)) if kept else 0.0,
        page_confidences=[round(c, 4) for c in page_confs],
    )
    if cache_path is not None:
        _store_cache(cache_path, pdf_path, params, result)
    return result
