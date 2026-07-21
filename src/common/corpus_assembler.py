"""
Objet intermédiaire commun aux deux voies (URDF, PDF) + assemblage vers
le schéma JSONL final des consignes.

Les deux adaptateurs (urdf_adapter, pdf_adapter) produisent un
DocumentDraft. L'assembleur est le SEUL endroit qui connaît le schéma de
sortie -- ajouter une source ne le change pas.

Schéma d'une ligne (consignes) :
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
    source_type: str          # "urdf" | "pdf_manual"
    text: str                 # texte final destiné au corpus
    license_status: str       # déjà classé (license_utils) : conforme / no-license / flagged:*
    url: str = ""
    lang: str = "en"
    source_name: str = ""     # ex: "robot_descriptions", "manual:unitree_g1"
    provenance: dict = field(default_factory=dict)  # infos annexes (capacités, fichiers...)


def assemble_record(
    draft: DocumentDraft,
    *,
    category: str = "cat3",
    tier: str = "D",
    token_counter: Optional[TokenCounter] = None,
) -> dict:
    """DocumentDraft -> ligne de corpus (dict prêt à sérialiser en JSONL)."""
    tc = token_counter or TokenCounter()
    return {
        "id": f"{category}-{draft.robot_id}-{draft.source_type}",
        "source": draft.source_name or draft.source_type,
        "category": category,
        "tier": tier,
        "license": draft.license_status,
        "url": draft.url,
        "lang": draft.lang,
        "text": draft.text,
        "n_tokens": tc.count(draft.text),
        "n_tokens_exact": tc.is_exact,     # False = comptage approximatif (voir tokenizer_utils)
        "source_type": draft.source_type,  # pratique pour les stats/filtrage
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }


REQUIRED_FIELDS = {"id", "source", "category", "tier", "license", "url",
                   "lang", "text", "n_tokens", "collected_at"}


def validate_record(record: dict) -> None:
    missing = REQUIRED_FIELDS - record.keys()
    if missing:
        raise ValueError(f"Champs manquants dans l'enregistrement : {sorted(missing)}")
    if not record["text"].strip():
        raise ValueError(f"Texte vide pour {record.get('id')}")
