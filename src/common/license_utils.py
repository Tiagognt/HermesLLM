"""
License classification, following the project's global rules: MIT / BSD
(all variants) / Apache-2.0 / CC-BY (all variants) -> allowed. Everything
else -> flagged, not collected by default. Absence of a license ->
"no-license", not collected by default either, unless an explicit decision
is recorded source by source in the relevant catalogue.
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
    Returns:
      - the SPDX id unchanged when the license is on the allowlist
      - "no-license" when no license was found for the source
      - "flagged:<spdx_id>" when a license exists but is not allowed
    """
    if not spdx_id:
        return "no-license"
    spdx_id = spdx_id.strip()
    if _ALLOWED_RE.match(spdx_id):
        return spdx_id
    return f"flagged:{spdx_id}"


def is_collectible(license_status: str, *, allow_no_license_override: bool = False) -> bool:
    """
    Default collection rule:
      - allowed license -> collect
      - "no-license" -> collect ONLY when explicitly authorised for this
        entry (allow_no_license_override=True); it stays tagged
        "no-license" in the metadata in every case
      - "flagged:*" -> never collected automatically
    """
    if license_status == "no-license":
        return allow_no_license_override
    if license_status.startswith("flagged:"):
        return False
    return True
