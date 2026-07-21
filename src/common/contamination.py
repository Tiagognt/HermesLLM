"""
Contamination check -- shared by cat1 / cat2 / cat3.

Global rule of the brief: *exclude from the training corpus any text that
overlaps the evaluation scenario* (here: a fire in a subway station). A
contaminated corpus makes the final evaluation meaningless: the model has
already seen the answer.

This module is deliberately DETERMINISTIC and auditable -- no LLM. A
rejected document must be defensible to a human: the verdict always carries
the rule that fired, the term found, and an excerpt of the offending text.

Two rule types (declared in contamination_scenarios.json):

  phrase        -- a scenario phrase appears verbatim.
  cooccurrence  -- at least one term from EACH group appears within the
                   same N-character window. This is what separates "fire"
                   in a safety manual (harmless) from "fire in a metro
                   station" (contaminating).

Use inside a pipeline:

    from common.contamination import ContaminationChecker
    checker = ContaminationChecker.from_config()
    verdict = checker.check(text)
    if verdict.is_contaminated:
        report.skip(item_id, reason=verdict.describe())

Use as an audit of an already-written corpus (the "contamination check
passed" deliverable of the definition of done):

    python3 src/common/contamination.py --corpus data/cat3/clean/corpus_clean.jsonl
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

if __name__ == "__main__":  # direct execution: src/ must be on sys.path
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import paths

CONFIG_PATH = Path(__file__).resolve().parent / "contamination_scenarios.json"


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------

def normalize(text: str) -> str:
    """
    Lowercase, accents stripped, whitespace collapsed.

    Stripping accents lets a single configured term catch both "métro" and
    "metro", "fumée" and "fumee" -- useful because our sources mix English,
    French and OCR output (where accents frequently disappear).
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    return re.sub(r"\s+", " ", text)


def _term_regex(term: str) -> re.Pattern:
    """
    Word-boundary search for the term, tolerating any whitespace between
    the words of a phrase (the text is already normalised, but PDF/OCR
    line breaks remain capricious).
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
                f"terms={self.terms} @{self.position}: « {self.excerpt} »")


@dataclass
class Verdict:
    matches: List[Match] = field(default_factory=list)

    @property
    def is_contaminated(self) -> bool:
        return bool(self.matches)

    def describe(self) -> str:
        if not self.matches:
            return "not contaminated"
        return " ; ".join(m.describe() for m in self.matches)


# --------------------------------------------------------------------------
# Rules
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
                break  # one occurrence is enough to document this phrase
        return out


class _CooccurrenceRule(_Rule):
    def __init__(self, scenario_id: str, spec: dict):
        super().__init__(scenario_id, spec)
        self.window = int(spec.get("window_chars", 400))
        self.groups: List[List[str]] = [list(g) for g in spec["groups"]]
        self._compiled = [[(t, _term_regex(t)) for t in g] for g in self.groups]

    def find(self, norm_text: str, first_only: bool) -> List[Match]:
        # Positions of every group hit, sorted: (position, term, group_index)
        hits: List[tuple] = []
        for gi, group in enumerate(self._compiled):
            for term, rx in group:
                for m in rx.finditer(norm_text):
                    hits.append((m.start(), term, gi))
        if not hits:
            return []
        n_groups = len(self._compiled)
        if len({gi for _, _, gi in hits}) < n_groups:
            return []  # a whole group is absent -> no co-occurrence

        hits.sort()
        out: List[Match] = []
        # Sliding window: look for an interval <= window containing at
        # least one term from each group.
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
                # Restart past the window so the same paragraph is not
                # reported fifty times.
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
                f"Contamination configuration not found: {path}. The "
                f"contamination check is a requirement of the brief; it must "
                f"not be disabled by a missing file."
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
                        f"Unknown rule type in {path}: {spec['type']!r} "
                        f"(expected one of {sorted(_RULE_TYPES)})"
                    )
                rules.append(factory(sid, spec))
        if not rules:
            raise ValueError(f"No active contamination rule in {path}.")
        return cls(rules, scenario_ids)

    def check(self, text: str, *, first_only: bool = True) -> Verdict:
        """
        first_only=True (default): stop at the first hit -- enough to decide
        exclusion, and much faster.
        first_only=False: full inventory, for auditing.
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
        return (f"{len(self.rules)} rules over "
                f"{len(self.scenario_ids)} scenario(s): "
                f"{', '.join(self.scenario_ids)}")


# --------------------------------------------------------------------------
# Command-line audit
# --------------------------------------------------------------------------

def audit_corpus(corpus_path: Path, *, first_only: bool = False) -> List[tuple]:
    """Returns [(record_id, Verdict)] for contaminated records."""
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
        description="Contamination audit of an already-written JSONL corpus.")
    ap.add_argument("--corpus", action="append", default=None,
                    help="path to a corpus_clean.jsonl (repeatable). "
                         "Default: every category corpus plus the merged one.")
    ap.add_argument("--text", default=None, help="test a string directly")
    args = ap.parse_args()

    checker = ContaminationChecker.from_config()
    print(f"Configuration: {CONFIG_PATH}")
    print(f"Active rules: {checker.describe()}\n")

    if args.text is not None:
        verdict = checker.check(args.text, first_only=False)
        print("CONTAMINATED" if verdict.is_contaminated else "clean")
        print(verdict.describe())
        sys.exit(1 if verdict.is_contaminated else 0)

    if args.corpus:
        corpora = [Path(c) for c in args.corpus]
    else:
        corpora = [paths.corpus_path(c) for c in paths.CATEGORIES]
        corpora.append(paths.full_corpus_path())

    total_flagged = 0
    for corpus in corpora:
        if not corpus.exists():
            print(f"[missing] {corpus}")
            continue
        flagged = audit_corpus(corpus)
        n_records = sum(1 for l in corpus.read_text(encoding="utf-8").splitlines()
                        if l.strip())
        state = "CONTAMINATED" if flagged else "clean"
        print(f"[{state}] {corpus} — {n_records} records, "
              f"{len(flagged)} flagged")
        for rid, verdict in flagged:
            print(f"    - {rid}")
            for m in verdict.matches:
                print(f"        {m.describe()}")
        total_flagged += len(flagged)

    print()
    if total_flagged:
        print(f"Contamination check FAILED: {total_flagged} record(s) to remove.")
    else:
        print("Contamination check: PASSED (no overlap detected).")
    sys.exit(1 if total_flagged else 0)


if __name__ == "__main__":
    _main()
