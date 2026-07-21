"""
Full-text retrieval of an arXiv paper -- category 2.

Two paths, selected per catalogue entry:

  html  since late 2023 arXiv publishes an HTML rendering of most papers.
        It is the better source: structure preserved, no columns to
        re-join, no hyphenated line breaks.
  pdf   fallback for older papers, through `pdftotext -layout` (poppler,
        already required by the project). arXiv PDFs always carry a text
        layer: no OCR is needed here, unlike the vendor manuals of cat3.

LICENSE: this module decides NOTHING. Each paper's license was verified
upstream through the arXiv OAI-PMH interface and frozen in `sources.py`;
`collect_hmrs.py` applies the barrier.

The bibliography is stripped: hundreds of lines of author names and page
numbers teach nothing about multi-agent robotics and would dilute the
corpus.
"""

from __future__ import annotations

import html as _html
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

USER_AGENT = "HermesLLM-corpus-builder/1.0 (research dataset construction)"
TIMEOUT = 90

_DROP_TAGS = re.compile(
    r"(?is)<(script|style|nav|footer|head|noscript|svg|math)\b.*?</\1>")
_ARTICLE = re.compile(r'(?is)<article[^>]*class="[^"]*ltx_document[^"]*".*?</article>')
_TAGS = re.compile(r"(?s)<[^>]+>")
_WS_LINE = re.compile(r"[ \t]+")
_BLANKS = re.compile(r"\n\s*\n+")

# Start of the bibliography, in rendered HTML as well as in PDF-extracted
# text.
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
    Truncate at the bibliography, but only if it appears in the last third
    of the document: some papers mention the word "References" in their
    introduction.
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
    # Block ends become newlines, otherwise the whole paper collapses onto
    # a single line.
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
        raise RuntimeError(f"{arxiv_id}: no usable HTML rendering "
                           f"({len(raw)} bytes)")
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
        raise RuntimeError(f"pdftotext failed on {arxiv_id}: "
                           f"{proc.stderr.strip()[:200]}")
    text = _strip_bibliography(_BLANKS.sub("\n\n", proc.stdout).strip())
    return PaperText(arxiv_id, text, "pdf", len(text), url)


MIN_USEFUL_CHARS = 4000     # a shorter "paper" means extraction failed


def fetch(arxiv_id: str, mode: str, tmp_dir: Path) -> PaperText:
    result = fetch_html(arxiv_id) if mode == "html" else fetch_pdf(arxiv_id, tmp_dir)
    if result.n_chars < MIN_USEFUL_CHARS:
        raise RuntimeError(
            f"{arxiv_id}: only {result.n_chars} characters through the "
            f"{mode} path -- extraction probably incomplete, paper dropped.")
    return result
