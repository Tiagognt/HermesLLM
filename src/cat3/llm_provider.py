"""
Interface LLM multi-fournisseur pour la phase 2, + garde-fou
anti-hallucination numérique.

Principe : la description en langage naturel est GÉNÉRÉE par un LLM, mais
tous les CHIFFRES viennent du parsing déterministe (urdf_parser). Le
garde-fou `verify_numbers` vérifie qu'aucun nombre du texte généré ne
sort de l'ensemble des valeurs autorisées (les grandeurs extraites) --
sinon on considère que le LLM a halluciné et on rejette / regénère.

Fournisseurs sélectionnables par variable d'env HERMES_LLM_PROVIDER
(anthropic | openai | gemini | template) ou par argument. Les clés API
sont lues dans l'environnement, jamais codées en dur :
  - anthropic -> ANTHROPIC_API_KEY
  - openai    -> OPENAI_API_KEY
  - gemini    -> GEMINI_API_KEY

Le fournisseur "template" ne fait AUCUN appel réseau : il produit une
description gabarit déterministe à partir des capacités. Il permet de
faire tourner toute la phase 2 hors ligne / sans clé (tests, CI, ou si on
ne veut pas de LLM du tout).
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Iterable, List, Optional, Tuple


# --------------------------------------------------------------------------
# Interface
# --------------------------------------------------------------------------

class LLMProvider:
    name = "base"

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        raise NotImplementedError


# --------------------------------------------------------------------------
# Fournisseurs réseau (clés lues dans l'env). Appels via urllib pour ne
# dépendre d'aucun SDK -- si vous préférez les SDK officiels, remplacez le
# corps de generate().
# --------------------------------------------------------------------------

class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, model: str = "claude-sonnet-4-6", max_tokens: int = 1024):
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        self.model, self.max_tokens = model, max_tokens

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        if not self.key:
            raise RuntimeError("ANTHROPIC_API_KEY absente de l'environnement.")
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode(),
            headers={
                "content-type": "application/json",
                "x-api-key": self.key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, model: str = "gpt-4o-mini", max_tokens: int = 1024):
        self.key = os.environ.get("OPENAI_API_KEY")
        self.model, self.max_tokens = model, max_tokens

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        if not self.key:
            raise RuntimeError("OPENAI_API_KEY absente de l'environnement.")
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
        body = {"model": self.model, "max_tokens": self.max_tokens, "messages": messages}
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"content-type": "application/json",
                     "authorization": f"Bearer {self.key}"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        return data["choices"][0]["message"]["content"]


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, model: str = "gemini-1.5-flash", max_tokens: int = 1024):
        self.key = os.environ.get("GEMINI_API_KEY")
        self.model, self.max_tokens = model, max_tokens

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        if not self.key:
            raise RuntimeError("GEMINI_API_KEY absente de l'environnement.")
        full = (system + "\n\n" if system else "") + prompt
        body = {"contents": [{"parts": [{"text": full}]}],
                "generationConfig": {"maxOutputTokens": self.max_tokens}}
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.model}:generateContent?key={self.key}")
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
        return "".join(p.get("text", "")
                       for p in data["candidates"][0]["content"]["parts"])


# --------------------------------------------------------------------------
# Fournisseur "template" : déterministe, hors ligne, sans clé.
# Utilisé par urdf_adapter pour produire une description gabarit si aucun
# LLM n'est configuré. Par construction, il n'introduit AUCUN chiffre qui
# ne soit déjà fourni -> il passe toujours le garde-fou.
# --------------------------------------------------------------------------

class TemplateProvider(LLMProvider):
    name = "template"

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        # Le prompt est ignoré : urdf_adapter appelle plutôt render_template()
        # directement. Ce generate() n'existe que pour respecter l'interface.
        return prompt


def get_provider(name: Optional[str] = None, **kw) -> LLMProvider:
    name = (name or os.environ.get("HERMES_LLM_PROVIDER", "template")).lower()
    return {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
        "gemini": GeminiProvider,
        "template": TemplateProvider,
    }.get(name, TemplateProvider)(**kw) if name != "template" else TemplateProvider()


# --------------------------------------------------------------------------
# Garde-fou anti-hallucination numérique
# --------------------------------------------------------------------------

_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def extract_numbers(text: str) -> List[float]:
    out = []
    for m in _NUM_RE.findall(text):
        try:
            out.append(float(m.replace(",", ".")))
        except ValueError:
            pass
    return out


def _matches_any(value: float, allowed: Iterable[float], rel_tol: float, abs_tol: float) -> bool:
    for a in allowed:
        if abs(value - a) <= max(abs_tol, rel_tol * abs(a)):
            return True
    return False


def verify_numbers(
    generated_text: str,
    allowed_values: Iterable[float],
    *,
    rel_tol: float = 0.02,
    abs_tol: float = 0.5,
    ignore_small_ints_up_to: int = 12,
) -> Tuple[bool, List[float]]:
    """
    Vérifie que chaque nombre du texte généré correspond (à tolérance près)
    à une valeur autorisée (les grandeurs extraites du URDF).

    - rel_tol / abs_tol : tolérance (le LLM peut arrondir 21.7 -> "22 kg").
    - ignore_small_ints_up_to : les petits entiers (1..N) sont tolérés même
      s'ils ne sont pas dans allowed_values -- ce sont souvent des tournures
      ("six axes", "3 doigts") ou des ordinaux, pas des grandeurs physiques.
      Mettre à 0 pour un contrôle strict.

    Retourne (ok, liste_des_nombres_suspects).
    """
    allowed = list(allowed_values)
    offending = []
    for v in extract_numbers(generated_text):
        if v.is_integer() and 0 <= v <= ignore_small_ints_up_to:
            continue
        if not _matches_any(v, allowed, rel_tol, abs_tol):
            offending.append(v)
    return (len(offending) == 0, offending)
