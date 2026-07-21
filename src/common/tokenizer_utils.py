"""
Token counting with the Qwen3 tokenizer (required by the project brief).

The tokenizer is downloaded from Hugging Face on first use. If HF is not
reachable (restricted network, offline CI), we fall back to an approximate
count and SAY SO (the n_tokens field of the corpus is then marked
approximate). Exact Qwen3 counting must run in an environment with access
to huggingface.co.

Usage:
    tc = TokenCounter()            # tries Qwen3, falls back otherwise
    n = tc.count("some text")
    tc.is_exact                    # True if Qwen3 loaded, False if fallback
"""

from __future__ import annotations

import re
from typing import Optional

# Reference model for the tokenizer. Adjustable if a different Qwen3
# repository is preferred.
DEFAULT_QWEN3_MODEL = "Qwen/Qwen3-8B"


class TokenCounter:
    def __init__(self, model: str = DEFAULT_QWEN3_MODEL, allow_fallback: bool = True):
        self.model = model
        self._tok = None
        self.is_exact = False
        try:
            from transformers import AutoTokenizer  # late import
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
        return "approximate (Qwen3 unavailable: no Hugging Face access)"


# Fallback: a reasonable approximation of sub-word counting. We count
# "word / punctuation / significant space" units and apply an average
# sub-word factor. Deliberately simple and deterministic.
_TOKENISH = re.compile(r"\w+|[^\w\s]", re.UNICODE)


def _approx_token_count(text: str) -> int:
    units = _TOKENISH.findall(text)
    # ~1.3 sub-tokens per "word" unit on average for technical English.
    return int(round(len(units) * 1.3))


def count_tokens(text: str, counter: Optional[TokenCounter] = None) -> int:
    return (counter or TokenCounter()).count(text)
