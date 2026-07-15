"""
Classification des licences selon les règles globales des consignes du
dataset : MIT / BSD (toutes variantes) / Apache-2.0 / CC-BY (toutes
variantes) -> autorisées. Tout le reste -> signalé, non collecté par
défaut. Absence de licence -> "no-license", non collecté par défaut sauf
décision explicite prise robot par robot dans sources.py.
"""

import re
from typing import Optional

_ALLOWED_PATTERNS = [
    r"^MIT$",
    r"^BSD-\d-Clause$",
    r"^Apache-2\.0$",
    r"^CC-BY-\d\.\d$",
]
_ALLOWED_RE = re.compile("|".join(_ALLOWED_PATTERNS))


def classify_license(spdx_id: Optional[str]) -> str:
    """
    Retourne :
      - le SPDX id tel quel si la licence est dans l'allowlist des consignes
      - "no-license" si aucune licence n'a été trouvée pour la source
      - "flagged:<spdx_id>" si une licence existe mais n'est pas autorisée
    """
    if not spdx_id:
        return "no-license"
    spdx_id = spdx_id.strip()
    if _ALLOWED_RE.match(spdx_id):
        return spdx_id
    return f"flagged:{spdx_id}"


def is_collectible(license_status: str, *, allow_no_license_override: bool = False) -> bool:
    """
    Règle de collecte par défaut :
      - licence autorisée -> collecte
      - "no-license" -> collecte SEULEMENT si explicitement autorisé pour
        cette entrée (allow_no_license_override=True) ; reste taggé
        "no-license" dans les métadonnées dans tous les cas
      - "flagged:*" -> jamais collecté automatiquement
    """
    if license_status == "no-license":
        return allow_no_license_override
    if license_status.startswith("flagged:"):
        return False
    return True
