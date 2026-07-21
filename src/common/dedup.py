"""
Déduplication exacte et quasi-exacte -- transverse cat1 / cat2 / cat3.

Les consignes imposent de retirer les doublons *exacts et approchés*. Sur
cat1 ce n'est pas un raffinement mais une nécessité mesurée : la
documentation Gazebo est publiée en 12 versions parallèles, celle de ROS 2
en une par distribution. Sur un échantillon `harmonic` vs `ionic`, ~85 %
des fichiers de même nom sont quasi identiques mais seulement ~15 % le sont
*au bit près* : un dédoublonnage par hachage exact laisserait donc passer
l'essentiel des doublons.

Deux niveaux :

  exact  -- SHA-256 du texte normalisé. Instantané, sans faux positif.
  proche -- MinHash + LSH par bandes, puis vérification du Jaccard estimé.
            Le LSH évite la comparaison quadratique : sur 10 000 documents,
            on ne compare qu'aux candidats tombés dans le même seau.

Déterminisme : les permutations MinHash sont tirées d'un PRNG à graine
fixe, et le hachage des shingles utilise crc32 (et non `hash()`, qui est
randomisé par processus). Deux exécutions produisent donc exactement le
même corpus.

Usage :

    index = DuplicateIndex(threshold=0.85)
    verdict = index.check(text)          # ne modifie pas l'index
    if verdict.is_duplicate:
        report.skip(doc_id, reason=verdict.describe())
    else:
        index.add(doc_id, text)
"""

from __future__ import annotations

import hashlib
import random
import re
import zlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

# Grand premier de Mersenne : arithmétique des permutations MinHash.
_MERSENNE_PRIME = (1 << 61) - 1
_MAX_HASH = (1 << 32) - 1

DEFAULT_NUM_PERM = 128
DEFAULT_BANDS = 16          # 16 bandes x 8 lignes -> seuil LSH ~0.84
DEFAULT_SHINGLE_SIZE = 5
DEFAULT_THRESHOLD = 0.85

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_for_hash(text: str) -> str:
    """
    Normalisation commune aux deux niveaux : minuscules, ponctuation
    retirée, espaces réduits. Deux pages qui ne diffèrent que par la
    ponctuation ou l'indentation sont ainsi vues comme identiques.
    """
    text = text.lower()
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def exact_hash(text: str) -> str:
    return hashlib.sha256(normalize_for_hash(text).encode("utf-8")).hexdigest()


def _shingles(text: str, k: int) -> Set[int]:
    """Ensemble des k-grammes de mots, hachés en crc32 (stable entre runs)."""
    words = normalize_for_hash(text).split()
    if not words:
        return set()
    if len(words) <= k:
        return {zlib.crc32(" ".join(words).encode("utf-8"))}
    return {
        zlib.crc32(" ".join(words[i:i + k]).encode("utf-8"))
        for i in range(len(words) - k + 1)
    }


class MinHasher:
    def __init__(self, num_perm: int = DEFAULT_NUM_PERM,
                 shingle_size: int = DEFAULT_SHINGLE_SIZE, seed: int = 20260721):
        self.num_perm = num_perm
        self.shingle_size = shingle_size
        rng = random.Random(seed)        # graine fixe -> signatures reproductibles
        self._params = [
            (rng.randint(1, _MERSENNE_PRIME - 1), rng.randint(0, _MERSENNE_PRIME - 1))
            for _ in range(num_perm)
        ]

    def signature(self, text: str) -> Tuple[int, ...]:
        sh = _shingles(text, self.shingle_size)
        if not sh:
            return tuple([_MAX_HASH] * self.num_perm)
        return tuple(
            min(((a * s + b) % _MERSENNE_PRIME) & _MAX_HASH for s in sh)
            for a, b in self._params
        )


def jaccard_estimate(sig_a: Sequence[int], sig_b: Sequence[int]) -> float:
    if not sig_a:
        return 0.0
    equal = sum(1 for x, y in zip(sig_a, sig_b) if x == y)
    return equal / len(sig_a)


@dataclass
class DuplicateVerdict:
    kind: str                      # "" | "exact" | "near"
    matched_key: Optional[str] = None
    similarity: float = 0.0

    @property
    def is_duplicate(self) -> bool:
        return bool(self.kind)

    def describe(self) -> str:
        if not self.kind:
            return "unique"
        if self.kind == "exact":
            return f"doublon exact de `{self.matched_key}`"
        return (f"quasi-doublon de `{self.matched_key}` "
                f"(similarité estimée {self.similarity:.2f})")


class DuplicateIndex:
    """
    Index incrémental. `check()` interroge sans modifier ; `add()` insère.
    Séparer les deux permet à l'appelant de journaliser puis de décider.
    """

    def __init__(self, *, threshold: float = DEFAULT_THRESHOLD,
                 num_perm: int = DEFAULT_NUM_PERM, bands: int = DEFAULT_BANDS,
                 shingle_size: int = DEFAULT_SHINGLE_SIZE):
        if num_perm % bands != 0:
            raise ValueError(f"num_perm ({num_perm}) doit être divisible "
                             f"par bands ({bands})")
        self.threshold = threshold
        self.bands = bands
        self.rows = num_perm // bands
        self.hasher = MinHasher(num_perm=num_perm, shingle_size=shingle_size)
        self._exact: Dict[str, str] = {}                 # hash -> clé
        self._signatures: Dict[str, Tuple[int, ...]] = {}
        self._buckets: Dict[Tuple[int, Tuple[int, ...]], List[str]] = {}

    # -- interne ------------------------------------------------------------

    def _band_keys(self, sig: Tuple[int, ...]):
        for b in range(self.bands):
            yield (b, sig[b * self.rows:(b + 1) * self.rows])

    # -- API ----------------------------------------------------------------

    def check(self, text: str) -> DuplicateVerdict:
        h = exact_hash(text)
        if h in self._exact:
            return DuplicateVerdict("exact", self._exact[h], 1.0)

        sig = self.hasher.signature(text)
        seen: Set[str] = set()
        best_key, best_sim = None, 0.0
        for band_key in self._band_keys(sig):
            for key in self._buckets.get(band_key, ()):
                if key in seen:
                    continue
                seen.add(key)
                # Le LSH ne donne que des CANDIDATS : on confirme toujours
                # par le Jaccard estimé avant de rejeter un document.
                sim = jaccard_estimate(sig, self._signatures[key])
                if sim > best_sim:
                    best_key, best_sim = key, sim
        if best_key is not None and best_sim >= self.threshold:
            return DuplicateVerdict("near", best_key, best_sim)
        return DuplicateVerdict("")

    def add(self, key: str, text: str) -> None:
        h = exact_hash(text)
        self._exact.setdefault(h, key)
        sig = self.hasher.signature(text)
        self._signatures[key] = sig
        for band_key in self._band_keys(sig):
            self._buckets.setdefault(band_key, []).append(key)

    def __len__(self) -> int:
        return len(self._signatures)

    def describe(self) -> str:
        return (f"MinHash {self.hasher.num_perm} permutations, "
                f"{self.bands} bandes x {self.rows} lignes, "
                f"seuil {self.threshold}")
