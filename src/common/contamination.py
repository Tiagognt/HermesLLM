"""
Contrôle de contamination -- transverse cat1 / cat2 / cat3.

Règle globale des consignes : *exclure du corpus d'entraînement tout texte
qui recoupe le scénario d'évaluation* (ici : incendie dans une station de
métro). Un corpus contaminé rend l'évaluation finale ininterprétable : le
modèle a déjà vu la réponse.

Ce module est volontairement DÉTERMINISTE et auditable -- aucun LLM. Un
document rejeté doit pouvoir être justifié devant quelqu'un : le verdict
porte toujours la règle déclenchée, le terme trouvé, et un extrait du
texte incriminé.

Deux types de règles (déclarés dans contamination_scenarios.json) :

  phrase        -- une phrase du scénario apparaît telle quelle.
  cooccurrence  -- au moins un terme de CHAQUE groupe apparaît dans une
                   même fenêtre de N caractères. C'est ce qui distingue
                   « incendie » dans un manuel de sécurité (inoffensif) de
                   « incendie dans une station de métro » (contaminant).

Utilisation dans un pipeline :

    from common.contamination import ContaminationChecker
    checker = ContaminationChecker.from_config()
    verdict = checker.check(text)
    if verdict.is_contaminated:
        report.skip(item_id, reason=verdict.describe())

Utilisation en audit d'un corpus déjà écrit (livrable « contamination
check passed » de la Definition of Done) :

    python3 src/common/contamination.py --corpus data/cat3/clean/corpus_clean.jsonl
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

if __name__ == "__main__":  # exécution directe : src/ doit être dans sys.path
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import paths

CONFIG_PATH = Path(__file__).resolve().parent / "contamination_scenarios.json"


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

def normalize(text: str) -> str:
    """
    Minuscules, accents retirés, espaces normalisés.

    Retirer les accents permet à un seul terme de config d'attraper
    « métro » et « metro », « fumée » et « fumee » -- utile car nos sources
    mélangent anglais, français et texte issu d'OCR (où les accents sautent
    fréquemment).
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    return re.sub(r"\s+", " ", text)


def _term_regex(term: str) -> re.Pattern:
    """
    Recherche du terme sur frontières de mot, en tolérant n'importe quelle
    espace entre les mots d'une expression (le texte a déjà été normalisé,
    mais les césures d'OCR/PDF restent capricieuses).
    """
    parts = [re.escape(p) for p in normalize(term).split()]
    return re.compile(r"\b" + r"\s+".join(parts) + r"\b")


# --------------------------------------------------------------------------
# Verdict
# --------------------------------------------------------------------------

@dataclass
class Match:
    scenario_id: str
    rule_id: str
    rule_type: str
    terms: List[str]
    position: int
    excerpt: str

    def describe(self) -> str:
        return (f"contamination [{self.scenario_id}/{self.rule_id}] "
                f"termes={self.terms} @{self.position} : « {self.excerpt} »")


@dataclass
class Verdict:
    matches: List[Match] = field(default_factory=list)

    @property
    def is_contaminated(self) -> bool:
        return bool(self.matches)

    def describe(self) -> str:
        if not self.matches:
            return "non contaminé"
        return " ; ".join(m.describe() for m in self.matches)


# --------------------------------------------------------------------------
# Règles
# --------------------------------------------------------------------------

EXCERPT_RADIUS = 90


def _excerpt(norm_text: str, position: int) -> str:
    start = max(0, position - EXCERPT_RADIUS)
    end = min(len(norm_text), position + EXCERPT_RADIUS)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(norm_text) else ""
    return prefix + norm_text[start:end].strip() + suffix


class _Rule:
    def __init__(self, scenario_id: str, spec: dict):
        self.scenario_id = scenario_id
        self.rule_id = spec.get("id", spec.get("type", "rule"))
        self.type = spec["type"]

    def find(self, norm_text: str, first_only: bool) -> List[Match]:
        raise NotImplementedError


class _PhraseRule(_Rule):
    def __init__(self, scenario_id: str, spec: dict):
        super().__init__(scenario_id, spec)
        self.phrases = list(spec["phrases"])
        self._compiled = [(p, _term_regex(p)) for p in self.phrases]

    def find(self, norm_text: str, first_only: bool) -> List[Match]:
        out: List[Match] = []
        for phrase, rx in self._compiled:
            for m in rx.finditer(norm_text):
                out.append(Match(self.scenario_id, self.rule_id, self.type,
                                 [phrase], m.start(),
                                 _excerpt(norm_text, m.start())))
                if first_only:
                    return out
                break  # une occurrence suffit à documenter cette phrase
        return out


class _CooccurrenceRule(_Rule):
    def __init__(self, scenario_id: str, spec: dict):
        super().__init__(scenario_id, spec)
        self.window = int(spec.get("window_chars", 400))
        self.groups: List[List[str]] = [list(g) for g in spec["groups"]]
        self._compiled = [[(t, _term_regex(t)) for t in g] for g in self.groups]

    def find(self, norm_text: str, first_only: bool) -> List[Match]:
        # Positions de chaque groupe, triées : (position, terme, index_groupe)
        hits: List[tuple] = []
        for gi, group in enumerate(self._compiled):
            for term, rx in group:
                for m in rx.finditer(norm_text):
                    hits.append((m.start(), term, gi))
        if not hits:
            return []
        n_groups = len(self._compiled)
        if len({gi for _, _, gi in hits}) < n_groups:
            return []  # un groupe entier est absent -> pas de cooccurrence

        hits.sort()
        out: List[Match] = []
        # Fenêtre glissante : on cherche un intervalle <= window contenant au
        # moins un terme de chaque groupe.
        left = 0
        counts: dict = {}
        for right in range(len(hits)):
            counts[hits[right][2]] = counts.get(hits[right][2], 0) + 1
            while hits[right][0] - hits[left][0] > self.window:
                counts[hits[left][2]] -= 1
                if counts[hits[left][2]] == 0:
                    del counts[hits[left][2]]
                left += 1
            if len(counts) == n_groups:
                window_hits = hits[left:right + 1]
                terms = sorted({t for _, t, _ in window_hits})
                pos = hits[left][0]
                out.append(Match(self.scenario_id, self.rule_id, self.type,
                                 terms, pos, _excerpt(norm_text, pos)))
                if first_only:
                    return out
                # On repart après la fenêtre pour ne pas signaler 50 fois le
                # même paragraphe.
                left = right + 1
                counts = {}
        return out


_RULE_TYPES = {"phrase": _PhraseRule, "cooccurrence": _CooccurrenceRule}


# --------------------------------------------------------------------------
# Checker
# --------------------------------------------------------------------------

class ContaminationChecker:
    def __init__(self, rules: List[_Rule], scenario_ids: List[str]):
        self.rules = rules
        self.scenario_ids = scenario_ids

    @classmethod
    def from_config(cls, config_path: Optional[Path] = None) -> "ContaminationChecker":
        path = config_path or CONFIG_PATH
        if not path.exists():
            raise FileNotFoundError(
                f"Configuration de contamination introuvable : {path}. "
                f"Le contrôle de contamination est une exigence des consignes, "
                f"il ne doit pas être désactivé par simple absence de fichier."
            )
        cfg = json.loads(path.read_text(encoding="utf-8"))
        rules: List[_Rule] = []
        scenario_ids: List[str] = []
        for scenario in cfg.get("scenarios", []):
            if not scenario.get("enabled", True):
                continue
            sid = scenario["id"]
            scenario_ids.append(sid)
            for spec in scenario.get("rules", []):
                factory = _RULE_TYPES.get(spec["type"])
                if factory is None:
                    raise ValueError(
                        f"Type de règle inconnu dans {path} : {spec['type']!r} "
                        f"(attendu : {sorted(_RULE_TYPES)})"
                    )
                rules.append(factory(sid, spec))
        if not rules:
            raise ValueError(f"Aucune règle de contamination active dans {path}.")
        return cls(rules, scenario_ids)

    def check(self, text: str, *, first_only: bool = True) -> Verdict:
        """
        first_only=True (défaut) : on s'arrête au premier indice trouvé --
        suffisant pour décider d'exclure, et bien plus rapide.
        first_only=False : inventaire complet, pour un audit.
        """
        norm = normalize(text)
        matches: List[Match] = []
        for rule in self.rules:
            found = rule.find(norm, first_only)
            if found:
                matches.extend(found)
                if first_only:
                    break
        return Verdict(matches)

    def describe(self) -> str:
        return (f"{len(self.rules)} règles sur "
                f"{len(self.scenario_ids)} scénario(s) : "
                f"{', '.join(self.scenario_ids)}")


# --------------------------------------------------------------------------
# Audit en ligne de commande
# --------------------------------------------------------------------------

def audit_corpus(corpus_path: Path, *, first_only: bool = False) -> List[tuple]:
    """Retourne [(record_id, Verdict)] pour les enregistrements contaminés."""
    checker = ContaminationChecker.from_config()
    flagged: List[tuple] = []
    for line in corpus_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        verdict = checker.check(rec.get("text", ""), first_only=first_only)
        if verdict.is_contaminated:
            flagged.append((rec.get("id", "?"), verdict))
    return flagged


def _main() -> None:
    import argparse
    import sys

    ap = argparse.ArgumentParser(
        description="Audit de contamination d'un corpus JSONL déjà écrit.")
    ap.add_argument("--corpus", action="append", default=None,
                    help="chemin d'un corpus_clean.jsonl (répétable). "
                         "Par défaut : les corpus de toutes les catégories.")
    ap.add_argument("--text", default=None, help="tester une chaîne directement")
    args = ap.parse_args()

    checker = ContaminationChecker.from_config()
    print(f"Configuration : {CONFIG_PATH}")
    print(f"Règles actives : {checker.describe()}\n")

    if args.text is not None:
        verdict = checker.check(args.text, first_only=False)
        print("CONTAMINÉ" if verdict.is_contaminated else "propre")
        print(verdict.describe())
        sys.exit(1 if verdict.is_contaminated else 0)

    if args.corpus:
        corpora = [Path(c) for c in args.corpus]
    else:
        corpora = [paths.corpus_path(c) for c in paths.CATEGORIES]

    total_flagged = 0
    for corpus in corpora:
        if not corpus.exists():
            print(f"[absent] {corpus}")
            continue
        flagged = audit_corpus(corpus)
        n_records = sum(1 for l in corpus.read_text(encoding="utf-8").splitlines()
                        if l.strip())
        state = "CONTAMINÉ" if flagged else "propre"
        print(f"[{state}] {corpus} — {n_records} enregistrements, "
              f"{len(flagged)} signalés")
        for rid, verdict in flagged:
            print(f"    - {rid}")
            for m in verdict.matches:
                print(f"        {m.describe()}")
        total_flagged += len(flagged)

    print()
    if total_flagged:
        print(f"ÉCHEC du contrôle de contamination : {total_flagged} "
              f"enregistrement(s) à retirer.")
    else:
        print("Contrôle de contamination : PASSÉ (aucun recoupement détecté).")
    sys.exit(1 if total_flagged else 0)


if __name__ == "__main__":
    _main()
