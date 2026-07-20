"""
Comptage de tokens avec le tokenizer Qwen3 (exigé par les consignes).

Le tokenizer se télécharge depuis Hugging Face au premier usage. Si HF
n'est pas accessible (réseau restreint, CI hors-ligne), on bascule sur un
repli approximatif et on le SIGNALE (le champ n_tokens du corpus est alors
marqué approximatif). Le comptage Qwen3 exact doit tourner dans un
environnement ayant accès à huggingface.co.

Usage :
    tc = TokenCounter()            # tente Qwen3, sinon repli
    n = tc.count("du texte")
    tc.is_exact                    # True si Qwen3 chargé, False si repli
"""

from __future__ import annotations

import re
from typing import Optional

# Modèle de référence pour le tokenizer. Ajustable si un dépôt Qwen3
# différent est souhaité.
DEFAULT_QWEN3_MODEL = "Qwen/Qwen3-8B"


class TokenCounter:
    def __init__(self, model: str = DEFAULT_QWEN3_MODEL, allow_fallback: bool = True):
        self.model = model
        self._tok = None
        self.is_exact = False
        try:
            from transformers import AutoTokenizer  # import tardif
            self._tok = AutoTokenizer.from_pretrained(model, trust_remote_code=True)
            self.is_exact = True
        except Exception as e:
            if not allow_fallback:
                raise
            self._reason = str(e)

    def count(self, text: str) -> int:
        if self._tok is not None:
            return len(self._tok.encode(text))
        return _approx_token_count(text)

    def describe(self) -> str:
        if self.is_exact:
            return f"Qwen3 exact ({self.model})"
        return "approximatif (Qwen3 indisponible : pas d'accès Hugging Face)"


# Repli : approximation raisonnable du comptage sous-mot. On compte les
# unités « mot / ponctuation / espace significatif » et on applique un
# facteur sous-mot moyen. Volontairement simple et déterministe.
_TOKENISH = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def _approx_token_count(text: str) -> int:
    units = _TOKENISH.findall(text)
    # ~1.3 sous-token par unité "mot" en moyenne pour du texte technique EN.
    return int(round(len(units) * 1.3))


def count_tokens(text: str, counter: Optional[TokenCounter] = None) -> int:
    return (counter or TokenCounter()).count(text)
