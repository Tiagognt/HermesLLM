"""
Récupération du texte intégral d'un article arXiv -- catégorie 2.

Deux voies, choisies par entrée du catalogue :

  html  arXiv publie depuis fin 2023 un rendu HTML de la plupart des
        articles. C'est la meilleure source : structure préservée, pas de
        colonnes à recoller, pas de coupures de mots.
  pdf   repli pour les articles antérieurs, via `pdftotext -layout`
        (poppler, déjà requis par le projet). Les PDF arXiv ont toujours une
        couche texte : aucun OCR n'est nécessaire ici, contrairement aux
        manuels constructeur de cat3.

LICENCE : ce module ne décide RIEN. La licence de chaque article a été
vérifiée en amont via l'interface OAI-PMH d'arXiv et figée dans
`sources.py` ; c'est `collect_hmrs.py` qui applique la barrière.

La bibliographie est retirée : des centaines de lignes d'auteurs et de
numéros de pages n'apprennent rien sur la robotique multi-agents et
dilueraient le corpus.
"""

from __future__ import annotations

import html as _html
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

USER_AGENT = "HermesLLM-corpus-builder/1.0 (research dataset construction)"
TIMEOUT = 90

_DROP_TAGS = re.compile(
    r"(?is)<(script|style|nav|footer|head|noscript|svg|math)\b.*?</\1>")
_ARTICLE = re.compile(r'(?is)<article[^>]*class="[^"]*ltx_document[^"]*".*?</article>')
_TAGS = re.compile(r"(?s)<[^>]+>")
_WS_LINE = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n\s*\n+")

# Début de bibliographie, en HTML rendu comme en texte extrait de PDF.
_BIB_MARKERS = re.compile(
    r"\n\s*(?:References|REFERENCES|Bibliography|BIBLIOGRAPHY)\s*\n")


@dataclass
class PaperText:
    arxiv_id: str
    text: str
    fetch: str
    n_chars: int
    source_url: str


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def _strip_bibliography(text: str) -> str:
    """
    Tronque à la bibliographie, mais seulement si elle apparaît dans le
    dernier tiers du document : certains articles citent le mot
    « References » dans leur introduction.
    """
    matches = list(_BIB_MARKERS.finditer(text))
    for m in matches:
        if m.start() > 0.55 * len(text):
            return text[:m.start()]
    return text


def html_to_text(raw_html: str) -> str:
    m = _ARTICLE.search(raw_html)
    body = m.group(0) if m else raw_html
    body = _DROP_TAGS.sub(" ", body)
    # Les fins de bloc deviennent des sauts de ligne, sinon tout l'article
    # se retrouve sur une seule ligne.
    body = re.sub(r"(?i)</(p|div|section|h\d|li|tr|figcaption)>", "\n", body)
    body = _TAGS.sub(" ", body)
    body = _html.unescape(body)
    body = _WS_LINE.sub(" ", body)
    body = "\n".join(line.strip() for line in body.split("\n"))
    return _BLANKS.sub("\n\n", body).strip()


def fetch_html(arxiv_id: str) -> PaperText:
    url = f"https://arxiv.org/html/{arxiv_id}"
    raw = _get(url).decode("utf-8", errors="replace")
    if "<article" not in raw and len(raw) < 5000:
        raise RuntimeError(f"{arxiv_id} : pas de rendu HTML exploitable "
                           f"({len(raw)} octets)")
    text = _strip_bibliography(html_to_text(raw))
    return PaperText(arxiv_id, text, "html", len(text), url)


def fetch_pdf(arxiv_id: str, tmp_dir: Path) -> PaperText:
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tmp_dir / f"{arxiv_id}.pdf"
    pdf_path.write_bytes(_get(url))
    proc = subprocess.run(["pdftotext", "-layout", str(pdf_path), "-"],
                          capture_output=True, text=True)
    pdf_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError(f"pdftotext a échoué sur {arxiv_id} : "
                           f"{proc.stderr.strip()[:200]}")
    text = _strip_bibliography(_BLANKS.sub("\n\n", proc.stdout).strip())
    return PaperText(arxiv_id, text, "pdf", len(text), url)


MIN_USEFUL_CHARS = 4000     # un article plus court n'a pas été extrait


def fetch(arxiv_id: str, mode: str, tmp_dir: Path) -> PaperText:
    result = fetch_html(arxiv_id) if mode == "html" else fetch_pdf(arxiv_id, tmp_dir)
    if result.n_chars < MIN_USEFUL_CHARS:
        raise RuntimeError(
            f"{arxiv_id} : {result.n_chars} caractères seulement par la voie "
            f"{mode} -- extraction probablement incomplète, article écarté.")
    return result
