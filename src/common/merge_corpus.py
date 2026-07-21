"""
Fusion des trois catégories en un corpus unique -- livrable final.

Les corpus par catégorie restent la SOURCE DE VÉRITÉ : ce module ne les
modifie jamais, il produit un dérivé régénérable dans `data/full/`. Toute
correction se fait dans la catégorie concernée, puis on refusionne.

La fusion n'est pas une simple concaténation. Elle applique les contrôles
qu'aucune catégorie ne peut faire seule :

  1. unicité des identifiants À TRAVERS les catégories ;
  2. déduplication CROISÉE -- cat1 et cat2 puisent toutes deux dans
     l'écosystème ROS, rien ne garantissait qu'un document n'apparaisse pas
     des deux côtés ;
  3. contamination, repassée sur le corpus assemblé (une ceinture de plus :
     chaque catégorie l'a déjà fait, mais le livrable doit être vérifiable
     seul) ;
  4. vérification du MÉLANGE imposé par les consignes
     (cat1 60-70 % · cat2 15-25 % · cat3 10-15 %), qui n'a de sens qu'ici.

Lançable depuis n'importe quel répertoire :
    python3 /chemin/vers/src/common/merge_corpus.py
    python3 .../merge_corpus.py --shuffle          # mélange déterministe
    python3 .../merge_corpus.py --no-cross-dedup
"""

from __future__ import annotations

import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

if __name__ == "__main__":  # exécution directe : src/ doit être dans sys.path
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import paths
from common.contamination import ContaminationChecker
from common.corpus_assembler import validate_record
from common.dedup import DuplicateIndex
from common.run_report import RunReport

# Bandes imposées par les consignes, par catégorie.
TARGET_MIX: Dict[str, Tuple[float, float]] = {
    "cat1": (0.60, 0.70),
    "cat2": (0.15, 0.25),
    "cat3": (0.10, 0.15),
}
SHUFFLE_SEED = 20260721


def load_category(category: str) -> List[dict]:
    path = paths.corpus_path(category)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def check_mix(by_cat_tokens: Counter) -> Tuple[bool, List[str]]:
    total = sum(by_cat_tokens.values())
    lines, ok = [], True
    for cat in ("cat1", "cat2", "cat3"):
        tok = by_cat_tokens.get(cat, 0)
        share = tok / total if total else 0.0
        lo, hi = TARGET_MIX[cat]
        verdict = "OK" if lo <= share <= hi else "HORS BANDE"
        if verdict != "OK":
            ok = False
        lines.append(f"| {cat} | {tok:,} | {share*100:.1f} % | "
                     f"{lo*100:.0f}–{hi*100:.0f} % | {verdict} |")
    return ok, lines


def write_stats(rows: List[dict], *, by_cat: Counter, by_cat_tokens: Counter,
                mix_ok: bool, mix_lines: List[str], dropped: Counter,
                dedup_desc: str, contamination_summary: str,
                report_path) -> None:
    total_tokens = sum(r["n_tokens"] for r in rows)
    by_tier: Counter = Counter()
    by_license: Counter = Counter()
    by_source_type: Counter = Counter()
    for r in rows:
        by_tier[r["tier"]] += r["n_tokens"]
        by_license[r["license"]] += 1
        by_source_type[r.get("source_type", "?")] += 1

    L = ["# Corpus complet RoboMix — statistiques", ""]
    L.append(f"- Généré le : {datetime.now(timezone.utc).isoformat()}")
    L.append(f"- Racine projet : `{paths.PROJECT_ROOT}`")
    L.append(f"- Enregistrements : {len(rows)}")
    L.append(f"- Tokens totaux : {total_tokens:,} (Qwen3)")
    L.append(f"- Contrôle de contamination : {contamination_summary}")
    L.append(f"- Déduplication croisée : {dedup_desc}")
    if report_path is not None:
        L.append(f"- Rapport d'exécution : `{paths.to_relative(report_path)}`")
    L.append("")

    L.append("## Mélange par catégorie (exigence des consignes)")
    L.append("")
    L.append("| Catégorie | Tokens | Part | Bande visée | Verdict |")
    L.append("|---|---:|---:|---:|---|")
    L.extend(mix_lines)
    L.append("")
    L.append(f"**Mélange global : {'CONFORME' if mix_ok else 'NON CONFORME'}**")
    L.append("")

    L.append("## Documents par catégorie")
    L.append("")
    L.append("| Catégorie | Documents | Tokens | Moyenne |")
    L.append("|---|---:|---:|---:|")
    for cat in ("cat1", "cat2", "cat3"):
        n = by_cat.get(cat, 0)
        t = by_cat_tokens.get(cat, 0)
        L.append(f"| {cat} | {n} | {t:,} | {t // n if n else 0} |")
    L.append(f"| **total** | **{len(rows)}** | **{total_tokens:,}** | "
             f"**{total_tokens // len(rows) if rows else 0}** |")
    L.append("")

    L.append("## Par tier")
    for tier in sorted(by_tier):
        L.append(f"- {tier} : {by_tier[tier]:,} tokens")
    L.append("")

    L.append("## Par licence")
    L.append("")
    L.append("| Licence | Documents |")
    L.append("|---|---:|")
    for lic in sorted(by_license, key=lambda x: -by_license[x]):
        flag = "  ← hors allowlist, inclusion sur décision tracée" \
            if lic == "no-license" or lic.startswith("flagged:") else ""
        L.append(f"| {lic}{flag} | {by_license[lic]} |")
    L.append("")

    L.append("## Par nature de source")
    for st in sorted(by_source_type, key=lambda x: -by_source_type[x]):
        L.append(f"- {st} : {by_source_type[st]} documents")
    L.append("")

    if dropped:
        L.append("## Écartés à la fusion")
        L.append("")
        L.append("| Motif | Nombre |")
        L.append("|---|---:|")
        for reason, n in dropped.most_common():
            L.append(f"| {reason} | {n} |")
        L.append("")

    L.append("## Régénération")
    L.append("")
    L.append("```bash")
    L.append("python3 src/cat1/build_corpus.py")
    L.append("python3 src/cat2/build_corpus.py")
    L.append("python3 src/cat3/build_corpus.py --sources urdf,pdf --ocr")
    L.append("python3 src/common/merge_corpus.py")
    L.append("```")
    L.append("")
    L.append("Les corpus par catégorie restent la source de vérité ; ce "
             "fichier en est un dérivé régénérable.")

    paths.full_stats_path().write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(
        description="Fusion des corpus cat1/cat2/cat3 en un corpus unique")
    ap.add_argument("--shuffle", action="store_true",
                    help="mélange déterministe (graine fixe) des enregistrements")
    ap.add_argument("--no-cross-dedup", action="store_true",
                    help="désactiver la déduplication entre catégories")
    ap.add_argument("--dedup-threshold", type=float, default=0.85)
    args = ap.parse_args()

    report = RunReport("merge-corpus", title="Corpus complet — fusion")
    checker = ContaminationChecker.from_config()
    index = DuplicateIndex(threshold=args.dedup_threshold)

    print(f"Racine projet : {paths.PROJECT_ROOT}")
    print(f"Contamination : {checker.describe()}")
    print(f"Dédup croisée : "
          f"{'désactivée' if args.no_cross_dedup else index.describe()}\n")

    kept: List[dict] = []
    seen_ids: set = set()
    dropped: Counter = Counter()
    by_cat: Counter = Counter()
    by_cat_tokens: Counter = Counter()

    for category in ("cat1", "cat2", "cat3"):
        rows = load_category(category)
        if not rows:
            print(f"  [{category}] corpus absent — catégorie ignorée")
            report.warn(category, reason=f"corpus absent : "
                                         f"{paths.corpus_path(category)}")
            continue

        n_kept = 0
        for rec in rows:
            try:
                validate_record(rec)
            except ValueError as exc:
                dropped["enregistrement invalide"] += 1
                report.fail(rec.get("id", "?"), kind=category, reason=str(exc))
                continue

            if rec["id"] in seen_ids:
                # Deux catégories ne doivent jamais produire le même id : ce
                # serait une collision de nommage, pas un doublon de contenu.
                dropped["identifiant en collision"] += 1
                report.fail(rec["id"], kind=category,
                            reason="identifiant déjà présent dans une autre "
                                   "catégorie — collision de nommage")
                continue

            verdict = checker.check(rec["text"])
            if verdict.is_contaminated:
                dropped["contamination"] += 1
                report.skip(rec["id"], kind=category,
                            reason=f"CONTAMINATION — {verdict.describe()}")
                continue

            if not args.no_cross_dedup:
                dup = index.check(rec["text"])
                if dup.is_duplicate:
                    dropped[f"doublon inter-catégories ({dup.kind})"] += 1
                    report.skip(rec["id"], kind=category,
                                reason=f"{dup.describe()} — déjà présent dans "
                                       f"le corpus fusionné")
                    continue
                index.add(rec["id"], rec["text"])

            seen_ids.add(rec["id"])
            kept.append(rec)
            by_cat[category] += 1
            by_cat_tokens[category] += rec["n_tokens"]
            n_kept += 1

        print(f"  [{category}] {len(rows)} lus -> {n_kept} retenus "
              f"({by_cat_tokens[category]:,} tokens)")
        report.ok(category, detail=f"{n_kept}/{len(rows)} retenus, "
                                   f"{by_cat_tokens[category]:,} tokens")

    if args.shuffle:
        # Graine fixe : deux fusions donnent le même ordre, sinon le corpus
        # n'est plus reproductible.
        random.Random(SHUFFLE_SEED).shuffle(kept)

    out = paths.full_corpus_path()
    paths.ensure_dirs(out.parent)
    with out.open("w", encoding="utf-8") as f:
        for rec in kept:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    mix_ok, mix_lines = check_mix(by_cat_tokens)
    total_tokens = sum(by_cat_tokens.values())
    contamination_summary = (
        f"PASSÉ — 0 recoupement sur {len(kept)} documents"
        if not dropped["contamination"]
        else f"{dropped['contamination']} document(s) exclu(s)")
    n_cross = sum(v for k, v in dropped.items() if k.startswith("doublon"))
    dedup_desc = ("désactivée" if args.no_cross_dedup
                  else f"{n_cross} doublon(s) inter-catégories retiré(s) "
                       f"({index.describe()})")

    report.info("Tokens totaux", f"{total_tokens:,}")
    report.info("Mélange", "CONFORME" if mix_ok else "NON CONFORME")
    report.info("Contamination", contamination_summary)
    report.info("Déduplication croisée", dedup_desc)
    report.info("Ordre", "mélangé (graine fixe)" if args.shuffle
                else "par catégorie")
    report_path = report.write()

    write_stats(kept, by_cat=by_cat, by_cat_tokens=by_cat_tokens,
                mix_ok=mix_ok, mix_lines=mix_lines, dropped=dropped,
                dedup_desc=dedup_desc,
                contamination_summary=contamination_summary,
                report_path=report_path)

    print(f"\nCorpus complet : {out}")
    print(f"  {len(kept)} enregistrements, {total_tokens:,} tokens")
    for line in mix_lines:
        print("   ", line)
    print(f"  mélange : {'CONFORME' if mix_ok else 'NON CONFORME'}")
    print(f"  contamination : {contamination_summary}")
    print(f"  dédup croisée : {dedup_desc}")
    if dropped:
        print(f"  écartés : {dict(dropped)}")
    print(f"  stats   : {paths.full_stats_path()}")
    print(f"  rapport : {report_path}")

    raise SystemExit(0 if mix_ok else 1)


if __name__ == "__main__":
    main()
