"""
Point d'entrée de la PHASE 2 (transformation) -- catégorie 2 (tier B).

Même enchaînement que cat1 : adaptation -> scrubbing -> contamination ->
déduplication -> comptage -> quotas -> assemblage.

UNE différence structurelle : le plafond des ARTICLES est porté par la
famille entière, pas par article. Chaque article est une « source » dans
les métadonnées ; leur appliquer un plafond individuel reviendrait à n'en
appliquer aucun. Les 43 articles se partagent donc un budget unique, réparti
en tourniquet sur les articles — on prend un morceau de chacun avant
d'approfondir, sinon les cinq premiers par ordre alphabétique
consommeraient tout.

Lançable depuis n'importe quel répertoire :
    python3 /chemin/vers/src/cat2/build_corpus.py
    python3 .../build_corpus.py --budget-scale 0.8
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> src/

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List

from common import paths
from common.contamination import ContaminationChecker
from common.corpus_assembler import DocumentDraft, assemble_record, validate_record
from common.dedup import DuplicateIndex
from common.quota import select_within_budget
from common.run_report import RunReport
from common.secret_scrubber import scrub
from common.tokenizer_utils import TokenCounter
from cat2 import text_adapters
from cat2.text_adapters import DocCandidate

CATEGORY = "cat2"
TIER = "B"
PAPER_FAMILY = "papers"
METADATA_PATH = paths.metadata_path(CATEGORY)
CORPUS_PATH = paths.corpus_path(CATEGORY)
STATS_PATH = paths.stats_path(CATEGORY)


def write_stats(rows: List[dict], *, skipped: Counter, per_bucket: Dict[str, dict],
                tc: TokenCounter, contamination_summary: str, dedup_desc: str,
                secrets: Counter, report_path) -> None:
    total_tokens = sum(r["n_tokens"] for r in rows)
    by_family: Counter = Counter()
    by_family_tok: Counter = Counter()
    by_license: Counter = Counter()
    by_kind: Counter = Counter()
    for r in rows:
        by_family[r["family"]] += 1
        by_family_tok[r["family"]] += r["n_tokens"]
        by_license[r["license"]] += 1
        by_kind[r["kind"]] += 1

    lines = ["# Corpus catégorie 2 — statistiques", ""]
    lines.append(f"- Généré le : {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Racine projet : `{paths.PROJECT_ROOT}`")
    lines.append(f"- Tier : {TIER}")
    lines.append(f"- Enregistrements : {len(rows)}")
    lines.append(f"- Tokens totaux : {total_tokens} "
                 f"({'Qwen3 exact' if tc.is_exact else 'APPROXIMATIF — ' + tc.describe()})")
    lines.append(f"- Contrôle de contamination : {contamination_summary}")
    lines.append(f"- Déduplication : {dedup_desc}")
    if report_path is not None:
        lines.append(f"- Rapport d'exécution : `{paths.to_relative(report_path)}`")
    lines.append("")

    lines.append("## Par famille de sources")
    lines.append("")
    lines.append("| Famille | Documents | Tokens | Part |")
    lines.append("|---|---:|---:|---:|")
    for fam in sorted(by_family_tok, key=lambda f: -by_family_tok[f]):
        pct = 100.0 * by_family_tok[fam] / total_tokens if total_tokens else 0
        lines.append(f"| {fam} | {by_family[fam]} | {by_family_tok[fam]:,} | {pct:.1f} % |")
    lines.append("")

    lines.append("## Par source (les 43 articles sont regroupés)")
    lines.append("")
    lines.append("| Source | Famille | Retenus | Tokens | Plafond | Écartés (quota) |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for sid in sorted(per_bucket, key=lambda s: -per_bucket[s]["tokens"]):
        d = per_bucket[sid]
        lines.append(f"| `{sid}` | {d['family']} | {d['kept']} | {d['tokens']:,} "
                     f"| {d['budget']:,} | {d['over_budget']} |")
    lines.append("")

    lines.append("## Par nature de contenu")
    for k in sorted(by_kind):
        lines.append(f"- {k} : {by_kind[k]} documents")
    lines.append("")

    lines.append("## Par licence")
    for lic in sorted(by_license):
        lines.append(f"- {lic} : {by_license[lic]}")
    lines.append("")

    lines.append("## Documents écartés")
    lines.append("")
    lines.append("| Motif | Nombre |")
    lines.append("|---|---:|")
    for reason, n in skipped.most_common():
        lines.append(f"| {reason} | {n} |")
    lines.append("")

    lines.append("## Secrets masqués")
    if secrets:
        for k, v in secrets.most_common():
            lines.append(f"- {k} : {v}")
    else:
        lines.append("- aucun secret détecté dans les sources retenues")

    STATS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 2 -- construction du corpus cat2")
    ap.add_argument("--budget-scale", type=float, default=1.0,
                    help="multiplie tous les plafonds")
    ap.add_argument("--dedup-threshold", type=float, default=0.85,
                    help="seuil de similarité du quasi-doublon (0 = désactivé)")
    args = ap.parse_args()

    report = RunReport("cat2-build-corpus", category=CATEGORY,
                       title="Catégorie 2 — phase 2 (construction du corpus)")

    if not METADATA_PATH.exists():
        raise SystemExit(f"Métadonnées absentes : {METADATA_PATH}\n"
                         f"-> lancez d'abord collect_hmrs.py")

    metas = [json.loads(l) for l in
             METADATA_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]

    tc = TokenCounter()
    checker = ContaminationChecker.from_config()
    index = DuplicateIndex(threshold=args.dedup_threshold)

    print(f"Racine projet : {paths.PROJECT_ROOT}")
    print(f"Sources       : {len(metas)}")
    print(f"Tokenizer     : {tc.describe()}")
    print(f"Contamination : {checker.describe()}")
    print(f"Déduplication : {index.describe()}")
    print(f"Échelle des plafonds : x{args.budget_scale}\n")
    for k, v in [("Sources", len(metas)), ("Tokenizer", tc.describe()),
                 ("Contamination", checker.describe()),
                 ("Déduplication", index.describe()),
                 ("Échelle des plafonds", f"x{args.budget_scale}")]:
        report.info(k, v)

    skipped: Counter = Counter()
    secrets: Counter = Counter()
    per_bucket: Dict[str, dict] = {}
    all_kept: List[tuple] = []
    # Les articles sont mis de côté : leur plafond est appliqué en une fois,
    # sur la famille entière (voir la docstring du module).
    paper_pool: List[tuple] = []
    paper_budget = 0

    for meta in metas:
        sid = meta["source_id"]
        root = paths.from_relative(meta["raw_dir"])
        if not root.exists():
            report.fail(sid, kind=meta["kind"],
                        reason=f"dossier brut absent : {root} — relancer la phase 1")
            continue
        try:
            candidates = text_adapters.adapt(meta, root)
        except Exception as exc:  # noqa: BLE001
            report.fail(sid, kind=meta["kind"], exc=exc)
            continue

        surviving: List[DocCandidate] = []
        for c in candidates:
            res = scrub(c.text)
            if res.n_redacted:
                for k, v in res.counts.items():
                    secrets[k] += v
                c.text = res.text
                c.flags["scrubbed"] = res.describe()

            verdict = checker.check(c.text)
            if verdict.is_contaminated:
                skipped["contamination"] += 1
                report.skip(c.doc_id, kind=meta["kind"],
                            reason=f"CONTAMINATION — {verdict.describe()}")
                continue

            if args.dedup_threshold > 0:
                dup = index.check(c.text)
                if dup.is_duplicate:
                    skipped[f"doublon {dup.kind}"] += 1
                    continue
                index.add(c.doc_id, c.text)

            c.n_tokens = tc.count(c.text)
            surviving.append(c)

        if meta["family"] == PAPER_FAMILY:
            paper_pool.extend((meta, c) for c in surviving)
            paper_budget = int(meta["token_budget"] * args.budget_scale)
            continue

        budget = int(meta["token_budget"] * args.budget_scale)
        kept, dropped = select_within_budget(surviving, budget)
        skipped["hors quota"] += len(dropped)
        per_bucket[sid] = {"family": meta["family"], "kept": len(kept),
                           "tokens": sum(c.n_tokens for c in kept),
                           "budget": budget, "over_budget": len(dropped)}
        all_kept.extend((meta, c) for c in kept)
        print(f"  [{sid:24s}] {len(candidates):4d} candidats -> "
              f"{len(surviving):4d} uniques -> {len(kept):4d} retenus "
              f"({per_bucket[sid]['tokens']:,} tokens)")
        report.ok(sid, kind=meta["kind"],
                  detail=f"{len(candidates)} candidats, {len(surviving)} uniques, "
                         f"{len(kept)} retenus, {per_bucket[sid]['tokens']:,} tokens")

    # ---- quota des articles, appliqué à la famille entière ---------------
    if paper_pool:
        cands = [c for _m, c in paper_pool]
        kept, dropped = select_within_budget(cands, paper_budget)
        kept_ids = {c.doc_id for c in kept}
        skipped["hors quota"] += len(dropped)
        n_papers = len({c.group for c in cands})
        n_kept_papers = len({c.group for c in kept})
        per_bucket[f"{n_papers} articles arXiv"] = {
            "family": PAPER_FAMILY, "kept": len(kept),
            "tokens": sum(c.n_tokens for c in kept),
            "budget": paper_budget, "over_budget": len(dropped)}
        all_kept.extend((m, c) for m, c in paper_pool if c.doc_id in kept_ids)
        print(f"  [{'articles arXiv':24s}] {len(cands):4d} candidats -> "
              f"{len(kept):4d} retenus, {n_kept_papers}/{n_papers} articles "
              f"représentés ({sum(c.n_tokens for c in kept):,} tokens)")
        report.ok("articles arXiv", kind="paper",
                  detail=f"{len(kept)} segments retenus sur {len(cands)}, "
                         f"{n_kept_papers}/{n_papers} articles représentés")

    # ---- écriture --------------------------------------------------------
    paths.ensure_dirs(CORPUS_PATH.parent)
    rows: List[dict] = []
    with CORPUS_PATH.open("w", encoding="utf-8") as f:
        for meta, c in all_kept:
            draft = DocumentDraft(
                robot_id=c.doc_id, source_type=c.kind, text=c.text,
                license_status=meta["license_status"], url=meta.get("url", ""),
                lang="en", source_name=meta["source_id"],
            )
            extra = {"family": c.family, "kind": c.kind, "rel_path": c.rel_path,
                     "repo_url": meta["repo_url"], "repo_commit": meta["repo_commit"]}
            if "part" in c.flags:
                extra["part"] = int(c.flags["part"])
                extra["n_parts"] = int(c.flags["n_parts"])
            if "arxiv_id" in c.flags:
                extra["arxiv_id"] = c.flags["arxiv_id"]
                extra["title"] = meta["display_name"]
            if "scrubbed" in c.flags:
                extra["scrubbed"] = c.flags["scrubbed"]
            rec = assemble_record(draft, category=CATEGORY, tier=TIER,
                                  token_counter=tc, doc_id=c.doc_id, extra=extra)
            rec["n_tokens"] = c.n_tokens
            validate_record(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows.append(rec)

    total_tokens = sum(r["n_tokens"] for r in rows)
    contamination_summary = (
        "PASSÉ — 0 recoupement" if not skipped["contamination"]
        else f"{skipped['contamination']} document(s) exclu(s)"
    ) + f" ({checker.describe()})"
    dedup_desc = (f"{skipped['doublon exact']} doublons exacts, "
                  f"{skipped['doublon near']} quasi-doublons retirés "
                  f"({index.describe()})")

    report.info("Résultat contamination", contamination_summary)
    report.info("Résultat déduplication", dedup_desc)
    report.info("Tokens retenus", f"{total_tokens:,}")
    report_path = report.write()

    write_stats(rows, skipped=skipped, per_bucket=per_bucket, tc=tc,
                contamination_summary=contamination_summary,
                dedup_desc=dedup_desc, secrets=secrets, report_path=report_path)

    print(f"\nCorpus écrit : {CORPUS_PATH}")
    print(f"  {len(rows)} enregistrements, {total_tokens:,} tokens (tier {TIER})")
    print(f"  contamination : {contamination_summary}")
    print(f"  déduplication : {dedup_desc}")
    if secrets:
        print(f"  secrets masqués : {dict(secrets)}")
    print(f"  rapport : {report_path}")


if __name__ == "__main__":
    main()
