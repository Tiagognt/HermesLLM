"""
OCR de PDF sans couche texte -- transverse cat1 / cat2 / cat3.

Contexte : trois manuels de la catégorie 3 sont des PDF *scannés* (images
seules). L'extraction pdfplumber/pdftotext en tire 0 caractère, et
pdf_adapter lève alors une erreur explicite plutôt que d'écrire un
enregistrement vide. Ce module fournit la voie de secours : rastériser
puis reconnaître le texte.

Chaîne de moteurs, essayés dans l'ordre :

  1. rapidocr-onnxruntime  -- installable par pip seul (ONNX embarqué),
     aucune dépendance système. C'est le moteur retenu ici parce que
     l'installation de tesseract exige les droits root, indisponibles sur
     cette machine.
  2. tesseract (via pytesseract, ou le binaire en repli) -- si un jour il
     est installé, il est préféré sur du texte purement latin.

La rastérisation passe par `pdftoppm` (poppler-utils), déjà requis par le
projet comme repli d'extraction texte.

AVERTISSEMENT IMPORTANT, à lire avant d'exploiter le résultat
--------------------------------------------------------------
L'OCR est faillible sur les CHIFFRES ("V1.0" lu "V1.o", "0.5" lu "O.5"),
or la règle n°1 du projet est qu'aucun chiffre du corpus ne doit être
douteux. Le texte produit ici n'est donc PAS de la même qualité qu'une
extraction native :

  - chaque document océrisé est marqué `ocr: true` dans le corpus, avec sa
    confiance moyenne, afin de rester filtrable en aval ;
  - les blocs sous le seuil de confiance sont écartés, pas devinés ;
  - on ne « corrige » jamais le texte reconnu : pas de post-traitement
    heuristique qui inventerait des caractères.

Utilisation :

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

# Version du format de cache : incrémenter invalide les caches existants
# (à faire si la chaîne d'OCR change et que le texte produit changerait).
CACHE_VERSION = 2

# Bornes de rastérisation. Certains « manuels » sont en réalité une page
# unique interminable (page produit chinoise déroulante) : le manuel G1 fait
# 20 x 784 pouces, soit 627 Mpx à 200 dpi -- assez pour faire tomber le
# décodeur d'images (garde-fou anti-« decompression bomb ») et, même sans
# cela, pour que le moteur OCR redimensionne l'image jusqu'à l'illisible.
# On borne donc la largeur, puis on découpe la hauteur en bandes.
MAX_RASTER_WIDTH_PX = 2000     # au-delà, le moteur redimensionne lui-même
MAX_BAND_HEIGHT_PX = 1600      # hauteur d'une bande envoyée à l'OCR
BAND_OVERLAP_PX = 120          # recouvrement, pour ne pas couper une ligne


class OcrUnavailable(RuntimeError):
    """Aucun moteur OCR utilisable dans cet environnement."""


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
        return (f"OCR {self.backend} : {self.n_pages_with_text}/{self.n_pages} "
                f"pages avec texte, confiance moyenne "
                f"{self.mean_confidence:.2f}, {len(self.text)} caractères"
                f"{' (cache)' if self.from_cache else ''}")


# --------------------------------------------------------------------------
# Garde-fou : est-ce seulement un PDF ?
# --------------------------------------------------------------------------

def looks_like_pdf(path: Path) -> bool:
    """
    Vérifie la signature %PDF- en tête de fichier.

    Cas réel rencontré : un manuel « .pdf » qui était en fait une page HTML
    enregistrée par le navigateur. Sans ce contrôle, l'erreur remontée est
    l'obscur « No /Root object! » de pdfminer, qui n'oriente vers aucune
    action. Ici on peut dire quoi faire : re-télécharger le fichier.
    """
    try:
        with path.open("rb") as f:
            return f.read(5) == b"%PDF-"
    except OSError:
        return False


def sniff_file_type(path: Path) -> str:
    """Description courte du contenu réel, pour un message d'erreur utile."""
    try:
        with path.open("rb") as f:
            head = f.read(1024)
    except OSError as exc:
        return f"illisible ({exc})"
    if head.startswith(b"%PDF-"):
        return "PDF"
    lowered = head.lstrip().lower()
    if lowered.startswith(b"<!doctype html") or lowered.startswith(b"<html"):
        return "HTML"
    if head.startswith(b"PK\x03\x04"):
        return "archive ZIP (docx/xlsx ?)"
    if head.startswith(b"\x89PNG"):
        return "image PNG"
    if head.startswith(b"\xff\xd8\xff"):
        return "image JPEG"
    return "inconnu"


# --------------------------------------------------------------------------
# Rastérisation
# --------------------------------------------------------------------------

def _pdfinfo(pdf_path: Path, *args: str) -> str:
    proc = subprocess.run(["pdfinfo", *args, str(pdf_path)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"pdfinfo a échoué sur {pdf_path.name} : {proc.stderr.strip()[:200]}")
    return proc.stdout


def count_pdf_pages(pdf_path: Path) -> int:
    m = re.search(r"^Pages:\s+(\d+)", _pdfinfo(pdf_path), re.MULTILINE)
    if not m:
        raise RuntimeError(f"Nombre de pages introuvable pour {pdf_path.name}")
    return int(m.group(1))


def page_size_pts(pdf_path: Path, page: int) -> Tuple[float, float]:
    out = _pdfinfo(pdf_path, "-f", str(page), "-l", str(page))
    m = re.search(r"Page(?:\s+\d+)?\s+size:\s+([\d.]+) x ([\d.]+) pts", out)
    if not m:
        raise RuntimeError(f"Taille de page introuvable pour {pdf_path.name} p{page}")
    return float(m.group(1)), float(m.group(2))


@dataclass
class _Band:
    """Une bande horizontale d'une page, en pixels à la résolution choisie."""
    y: int
    height: int


def plan_page_render(pdf_path: Path, page: int, dpi: int) -> Tuple[int, int, int, List[_Band]]:
    """
    Retourne (dpi_effectif, largeur_px, hauteur_px, bandes).

    Le dpi est abaissé si nécessaire pour que la largeur reste sous
    MAX_RASTER_WIDTH_PX, puis la hauteur est découpée en bandes qui se
    recouvrent. Une page normale donne une seule bande couvrant toute la
    page : le chemin nominal est inchangé.
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
            f"pdftoppm a échoué sur {pdf_path.name} page {page} "
            f"bande {index} : {proc.stderr.strip()[:200]}"
        )
    produced = sorted(out_dir.glob(f"p{page:05d}b{index:05d}*.png"))
    return produced[0] if produced else None


def _merge_bands(texts: List[str]) -> str:
    """
    Recolle les bandes en supprimant les lignes dupliquées par le
    recouvrement. On ne retire qu'une ligne strictement identique à la
    précédente : aucune reconstruction, aucune correction.
    """
    merged: List[str] = []
    for text in texts:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if merged and stripped == merged[-1]:
                continue
            # Le recouvrement peut ramener plusieurs lignes déjà vues juste
            # avant : on regarde une courte fenêtre arrière.
            if stripped in merged[-4:]:
                continue
            merged.append(stripped)
    return "\n".join(merged)


# --------------------------------------------------------------------------
# Moteurs
# --------------------------------------------------------------------------

class _Backend:
    name = "base"

    def available(self) -> bool:
        raise NotImplementedError

    def read_image(self, image: Path, min_confidence: float) -> tuple:
        """Retourne (texte_de_la_page, confiance_moyenne)."""
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

        # res : [[box, texte, score], ...]. On regroupe par ligne (centre y)
        # puis on ordonne de gauche à droite : l'ordre de lecture n'est pas
        # garanti par le détecteur.
        items = []
        for box, text, score in res:
            if score < min_confidence:
                continue          # bloc douteux : écarté, jamais deviné
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
            return True   # on sait utiliser le binaire directement

    def read_image(self, image: Path, min_confidence: float) -> tuple:
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            proc = subprocess.run(["tesseract", str(image), "stdout"],
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"tesseract a échoué : {proc.stderr[:200]}")
            # Le mode binaire ne remonte pas de confiance exploitable.
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
                        f"Moteur OCR demandé indisponible : {preferred}")
                return b
        raise OcrUnavailable(
            f"Moteur OCR inconnu : {preferred} "
            f"(connus : {[b.name for b in backends]})")
    for b in backends:
        if b.available():
            return b
    raise OcrUnavailable(
        "Aucun moteur OCR disponible. Installez au choix :\n"
        "  pip install rapidocr-onnxruntime      (aucun droit root requis)\n"
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
        return None      # le PDF a changé -> cache périmé
    if blob.get("params") != params:
        return None      # dpi / seuil / moteur différent -> on refait
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
# Entrée principale
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
    Océrise un PDF page par page et retourne le texte reconnu.

    max_pages : borne le coût (l'OCR tourne à quelques secondes par page en
    CPU). Si le PDF est plus long, les pages au-delà sont ignorées -- et le
    fait est signalé dans le texte produit, jamais tu.
    cache_path : si fourni, le résultat est relu/écrit là, de sorte que
    régénérer le corpus ne relance pas l'OCR (phases indépendantes).
    """
    if not looks_like_pdf(pdf_path):
        raise RuntimeError(
            f"{pdf_path.name} n'est pas un PDF (contenu détecté : "
            f"{sniff_file_type(pdf_path)}). Le fichier doit être "
            f"re-téléchargé depuis la source."
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
        body += (f"\n\n[... {total_pages - n_pages} pages non océrisées "
                 f"(limite max_pages={max_pages}) ...]")

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
