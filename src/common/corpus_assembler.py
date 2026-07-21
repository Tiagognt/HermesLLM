"""
Intermediate object shared by every collection path, plus assembly into the
final JSONL schema required by the project brief.

All adapters (urdf_adapter, pdf_adapter, and the cat1/cat2 text adapters)
produce a DocumentDraft. The assembler is the ONLY place that knows the
output schema -- adding a source never changes it.

Schema of one line (per the brief):
  {id, source, category, tier, license, url, lang, text, n_tokens, collected_at}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from common.tokenizer_utils import TokenCounter


@dataclass
class DocumentDraft:
    robot_id: str
    source_type: str          # "urdf" | "pdf_manual" | "docs" | "code" | ...
    text: str                 # final text destined for the corpus
    license_status: str       # already classified (license_utils):
                              # allowed / no-license / flagged:*
    url: str = ""
    lang: str = "en"
    source_name: str = ""     # e.g. "robot_descriptions", "manual:unitree_g1"
    provenance: dict = field(default_factory=dict)  # side info (capabilities, files...)
    # Text produced by optical character recognition (scanned PDF): lower
    # quality and lower digit reliability than a native extraction. Carried
    # into the corpus so it stays filterable downstream (see common/ocr.py).
    ocr: bool = False
    ocr_confidence: Optional[float] = None


def assemble_record(
    draft: DocumentDraft,
    *,
    category: str = "cat3",
    tier: str = "D",
    token_counter: Optional[TokenCounter] = None,
    doc_id: Optional[str] = None,
    extra: Optional[dict] = None,
) -> dict:
    """
    DocumentDraft -> corpus line (dict ready to serialise as JSONL).

    doc_id: replaces `robot_id` when building the identifier, for categories
    whose unit is not a robot (cat1/cat2: a document).
    extra: additional fields merged into the record, WITHOUT being able to
    overwrite a field of the required schema -- this is the per-category
    extension point (cat1/cat2 put family/kind/rel_path there).
    """
    tc = token_counter or TokenCounter()
    record = {
        "id": f"{category}-{doc_id or draft.robot_id}-{draft.source_type}",
        "source": draft.source_name or draft.source_type,
        "category": category,
        "tier": tier,
        "license": draft.license_status,
        "url": draft.url,
        "lang": draft.lang,
        "text": draft.text,
        "n_tokens": tc.count(draft.text),
        "n_tokens_exact": tc.is_exact,     # False = approximate count (see tokenizer_utils)
        "source_type": draft.source_type,  # handy for stats / filtering
        "ocr": draft.ocr,                  # True = optically recognised text
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }
    if draft.ocr and draft.ocr_confidence is not None:
        record["ocr_confidence"] = round(draft.ocr_confidence, 4)
    if extra:
        protected = REQUIRED_FIELDS & extra.keys()
        if protected:
            raise ValueError(
                f"`extra` attempts to overwrite schema fields: {sorted(protected)}")
        record.update(extra)
    return record


REQUIRED_FIELDS = {"id", "source", "category", "tier", "license", "url",
                   "lang", "text", "n_tokens", "collected_at"}


def validate_record(record: dict) -> None:
    missing = REQUIRED_FIELDS - record.keys()
    if missing:
        raise ValueError(f"Missing fields in record: {sorted(missing)}")
    if not record["text"].strip():
        raise ValueError(f"Empty text for {record.get('id')}")
