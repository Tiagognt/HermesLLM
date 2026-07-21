"""
Retrait des secrets dans le texte collecté -- transverse cat1 / cat2 / cat3.

Exigence des consignes pour la catégorie 1 : *scrub API keys/secrets from
code*. Un corpus d'entraînement ne doit pas mémoriser de credential : un
LLM entraîné dessus peut le restituer.

Le module remplace la valeur par un marqueur explicite plutôt que de
supprimer la ligne : le contexte pédagogique (« voici comment on passe une
clé d'API ») reste lisible, seule la valeur disparaît.

Chaque substitution est comptée et remontée à l'appelant, jamais
silencieuse (règle 4).

Faux positifs assumés : on préfère masquer une chaîne anodine que laisser
fuir un vrai secret. Les valeurs manifestement fictives des documentations
(`YOUR_API_KEY`, `xxx`, `<token>`...) sont toutefois épargnées, sinon la
moitié des tutoriels ROS ressortirait caviardée.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Pattern, Tuple

# Valeurs de remplacement pédagogiques -- à ne PAS masquer.
_PLACEHOLDER_RE = re.compile(
    r"^(your[_-]?|my[_-]?|some[_-]?|example[_-]?|dummy|fake|test|sample|"
    r"changeme|placeholder|insert|todo|xxx+|\.\.\.|<.*>|\{\{.*\}\}|\$\{.*\}|"
    r"\$[A-Z_]+|None|null|true|false|\d+)",
    re.IGNORECASE,
)


def _is_placeholder(value: str) -> bool:
    v = value.strip().strip("'\"")
    if len(v) < 8:
        return True
    if _PLACEHOLDER_RE.match(v):
        return True
    # Une valeur sans aucune variété (aaaaaaaa, 00000000) n'est pas un secret.
    return len(set(v)) <= 2


@dataclass
class ScrubResult:
    text: str
    counts: Dict[str, int] = field(default_factory=dict)

    @property
    def n_redacted(self) -> int:
        return sum(self.counts.values())

    def describe(self) -> str:
        if not self.counts:
            return "aucun secret détecté"
        detail = ", ".join(f"{k}×{v}" for k, v in sorted(self.counts.items()))
        return f"{self.n_redacted} secret(s) masqué(s) : {detail}"


# (nom, motif, groupe_de_la_valeur_ou_0)
# groupe 0 => tout le motif est remplacé ; sinon seule la valeur l'est.
_RULES: List[Tuple[str, Pattern, int]] = [
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), 0),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), 0),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), 0),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), 0),
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), 0),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\."
                       r"[A-Za-z0-9_\-]{10,}\b"), 0),
    ("private_key_block",
     re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
                re.DOTALL), 0),
    # Affectation générique : api_key = "..." / password: '...' / token=...
    ("assigned_secret",
     re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key|secret|password|passwd|"
                r"pwd|access[_-]?token|auth[_-]?token|token|bearer)\b"
                r"\s*[:=]\s*[\"']([^\"'\n]{8,})[\"']"), 1),
    # URL contenant des identifiants : https://user:motdepasse@host
    ("url_credentials",
     re.compile(r"(?<=://)([^/\s:@]+:[^/\s:@]+)(?=@)"), 1),
]

_MARKER = "[REDACTED_{}]"


def scrub(text: str) -> ScrubResult:
    counts: Dict[str, int] = {}

    for name, pattern, group in _RULES:
        def _replace(m: re.Match, _name=name, _group=group) -> str:
            value = m.group(_group) if _group else m.group(0)
            if _group and _is_placeholder(value):
                return m.group(0)          # valeur d'exemple : on la garde
            counts[_name] = counts.get(_name, 0) + 1
            marker = _MARKER.format(_name.upper())
            if _group == 0:
                return marker
            start, end = m.start(_group) - m.start(0), m.end(_group) - m.start(0)
            whole = m.group(0)
            return whole[:start] + marker + whole[end:]

        text = pattern.sub(_replace, text)

    return ScrubResult(text, counts)
