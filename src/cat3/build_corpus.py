"""
Point d'entrée de la phase 2 (transformation) -- catégorie 3.

Lit les bruts de la phase 1 (URDF collectés + manuels PDF déposés
manuellement), applique la barrière licence, produit un corpus JSONL
unifié (1 enregistrement par source) + des statistiques.

Lançable depuis n'importe quel répertoire :
    python3 /chemin/vers/src/cat3/build_corpus.py
    python3 .../build_corpus.py --sources urdf,pdf
    python3 .../build_corpus.py --provider gemini
    python3 .../build_corpus.py --sources pdf --allow-proprietary-pdf

Contrairement à la version précédente, AUCUN saut n'est silencieux :
chaque robot ignoré (manuel absent, licence non conforme, extraction
vide) est journalisé et compté dans le rapport final.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> src/

import argparse
import json
from collections import Counter
from datetime import datetime, timezone

from common import paths
from common.contamination import ContaminationChecker
from common.license_utils import classify_license, is_collectible
from common.llm_provider import get_provider
from common.run_report import RunReport
from common.tokenizer_utils import TokenCounter
from common.corpus_assembler import assemble_record, validate_record
from cat3 import urdf_adapter, pdf_adapter

CATEGORY = "cat3"
METADATA_PATH = paths.metadata_path(CATEGORY)
MANUALS_DIR = paths.raw_kind_dir(CATEGORY, "manuals")
CORPUS_PATH = paths.corpus_path(CATEGORY)
STATS_PATH = paths.stats_path(CATEGORY)

# Le manifeste est de la CONFIGURATION : il vit avec le code. On tolère
# l'ancien emplacement (dans les données) pour ne rien casser, en le signalant.
MANIFEST_PATH = paths.code_dir(CATEGORY) / "pdf_manifest.json"
LEGACY_MANIFEST_PATH = MANUALS_DIR / "pdf_manifest.json"

ALLOW_NO_LICENSE_FOR = {"agilex_ranger_mini_v3"}


def _resolve_manifest() -> Path | None:
    if MANIFEST_PATH.exists():
        return MANIFEST_PATH
    if LEGACY_MANIFEST_PATH.exists():
        print(f"  [note] manifeste trouvé à l'ancien emplacement "
              f"({LEGACY_MANIFEST_PATH}). Emplacement recommandé : {MANIFEST_PATH}")
        return LEGACY_MANIFEST_PATH
    return None


# --------------------------------------------------------------------------
# Voie URDF
# --------------------------------------------------------------------------

def _iter_urdf(provider, drafts: list, skipped: list, report: RunReport) -> None:
    if not METADATA_PATH.exists():
        print(f"  [urdf] aucun fichier de métadonnées : {METADATA_PATH}")
        print("         -> lancez d'abord collect_pilot.py")
        report.fail("(voie urdf)", kind="urdf",
                    reason=f"métadonnées absentes : {METADATA_PATH} — "
                           f"lancer collect_pilot.py d'abord")
        return

    for line in METADATA_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        meta = json.loads(line)
        rid = meta["robot_id"]
        status = meta["license_status"]

        if not is_collectible(status, allow_no_license_override=rid in ALLOW_NO_LICENSE_FOR):
            reason = f"licence non conforme ({status})"
            skipped.append((rid, "urdf", reason))
            report.skip(rid, kind="urdf", reason=reason)
            continue

        urdf_path = paths.from_relative(meta["raw_urdf_path"])
        if not urdf_path.exists():
            reason = f"fichier absent : {urdf_path}"
            skipped.append((rid, "urdf", reason))
            report.skip(rid, kind="urdf", reason=reason)
            continue

        try:
            draft = urdf_adapter.adapt(
                rid, urdf_path,
                license_status=status,
                url=meta.get("repo_url", ""),
                source_name=meta.get("source_type", "robot_descriptions"),
                provider=provider,
            )
        except Exception as exc:  # un URDF cassé n'arrête pas le run
            skipped.append((rid, "urdf", f"ECHEC : {exc}"))
            report.fail(rid, kind="urdf", exc=exc)
            continue

        for note in draft.provenance.get("parse_notes", []):
            report.warn(rid, kind="urdf", reason=note)
        drafts.append(draft)


# --------------------------------------------------------------------------
# Voie PDF
# --------------------------------------------------------------------------

def _iter_pdf(provider, drafts: list, skipped: list, report: RunReport, *,
              allow_proprietary: bool, llm_format: bool,
              use_ocr: bool, ocr_max_pages) -> None:
    manifest_path = _resolve_manifest()
    if manifest_path is None:
        print(f"  [pdf] manifeste introuvable. Attendu : {MANIFEST_PATH}")
        report.fail("(voie pdf)", kind="pdf_manual",
                    reason=f"manifeste introuvable, attendu : {MANIFEST_PATH}")
        return

    manuals = json.loads(manifest_path.read_text(encoding="utf-8"))["manuals"]
    print(f"  [pdf] manifeste : {manifest_path} ({len(manuals)} entrées)")
    print(f"  [pdf] dossier des manuels : {MANUALS_DIR}")
    report.info("Manifeste PDF", f"`{paths.to_relative(manifest_path)}` "
                                 f"({len(manuals)} entrées)")

    for m in manuals:
        rid = m["robot_id"]
        robot_dir = MANUALS_DIR / rid
        pdf_path = pdf_adapter.find_pdf(robot_dir, m.get("target_filename"))

        if pdf_path is None:
            reason = f"aucun .pdf dans {paths.to_relative(robot_dir)}"
            skipped.append((rid, "pdf_manual", reason))
            report.skip(rid, kind="pdf_manual", reason=reason)
            continue

        status = classify_license(m.get("license_spdx"))
        # Décision par robot dans le manifeste, ou globale via l'option CLI.
        per_entry = bool(m.get("allow_no_license", False))
        override = per_entry or allow_proprietary
        if not is_collectible(status, allow_no_license_override=override):
            reason = (f"licence non conforme ({status}) -- utilisez "
                      f"--allow-proprietary-pdf ou allow_no_license dans le manifeste")
            skipped.append((rid, "pdf_manual", reason))
            report.skip(rid, kind="pdf_manual", reason=reason)
            continue

        def _progress(page, total, conf, info=None, _rid=rid):
            extra = ""
            if info:
                if info.get("bands"):
                    extra = f" bande {info['band']}/{info['bands']}"
                extra += f" @{info.get('dpi')}dpi"
            print(f"  [pdf] {_rid} OCR page {page}/{total}{extra} "
                  f"(confiance {conf:.2f})", flush=True)

        try:
            draft = pdf_adapter.adapt(
                rid, pdf_path,
                license_status=status,
                url=m.get("url", ""),
                source_name=f"manual:{rid}",
                provider=provider,
                use_llm_format=llm_format,
                use_ocr=use_ocr,
                ocr_max_pages=ocr_max_pages,
                ocr_progress=_progress,
            )
        except Exception as exc:  # PDF corrompu / scanné -> journalisé, on continue
            skipped.append((rid, "pdf_manual", f"ECHEC : {exc}"))
            report.fail(rid, kind="pdf_manual", exc=exc)
            continue

        drafts.append(draft)
        print(f"  [pdf] {rid} <- {pdf_path.name}"
              f"{' [OCR]' if draft.ocr else ''}")
        if status == "no-license":
            origin = ("manifeste (allow_no_license)" if per_entry
                      else "option --allow-proprietary-pdf")
            report.warn(rid, kind="pdf_manual",
                        reason=f"manuel sans licence conforme inclus sur "
                               f"décision explicite — {origin} ; "
                               f"{m.get('license_note', '')}")
        if draft.ocr:
            report.warn(rid, kind="pdf_manual",
                        reason=f"texte issu d'OCR "
                               f"({draft.provenance.get('ocr_backend')}, "
                               f"confiance moyenne "
                               f"{draft.provenance.get('ocr_mean_confidence')}) "
                               f"— fiabilité des chiffres inférieure à une "
                               f"extraction native")


# --------------------------------------------------------------------------
# Statistiques
# --------------------------------------------------------------------------

def write_stats(rows: list, skipped: list, tc: TokenCounter, *,
                contamination_summary: str, report_path=None) -> None:
    by_type = Counter(r["source_type"] for r in rows)
    tokens_by_type: Counter = Counter()
    for r in rows:
        tokens_by_type[r["source_type"]] += r["n_tokens"]
    total_tokens = sum(r["n_tokens"] for r in rows)
    by_license = Counter(r["license"] for r in rows)
    ocr_rows = [r for r in rows if r.get("ocr")]

    lines = ["# Corpus catégorie 3 — statistiques", ""]
    lines.append(f"- Généré le : {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Racine projet : `{paths.PROJECT_ROOT}`")
    lines.append(f"- Enregistrements : {len(rows)}")
    lines.append(f"- Tokens totaux : {total_tokens} "
                 f"({'Qwen3 exact' if tc.is_exact else 'APPROXIMATIF — ' + tc.describe()})")
    lines.append(f"- Contrôle de contamination : {contamination_summary}")
    if report_path is not None:
        lines.append(f"- Rapport d'exécution : `{paths.to_relative(report_path)}`")
    lines.append("")

    lines.append("## Par type de source")
    for t in sorted(by_type):
        n = by_type[t]
        moy = tokens_by_type[t] // n if n else 0
        lines.append(f"- {t} : {n} enregistrements, {tokens_by_type[t]} tokens "
                     f"(moyenne {moy})")

    lines.append("")
    lines.append("## Par licence")
    for lic in sorted(by_license):
        marker = "  ← hors allowlist, inclusion sur décision explicite" \
            if lic == "no-license" or lic.startswith("flagged:") else ""
        lines.append(f"- {lic} : {by_license[lic]}{marker}")

    lines.append("")
    lines.append("## Qualité d'extraction")
    lines.append(f"- Extraction native : {len(rows) - len(ocr_rows)}")
    lines.append(f"- Texte issu d'OCR : {len(ocr_rows)}"
                 + (" (champ `ocr: true`, filtrable)" if ocr_rows else ""))
    for r in ocr_rows:
        lines.append(f"  - `{r['id']}` — confiance moyenne "
                     f"{r.get('ocr_confidence')}")

    if skipped:
        lines.append("")
        lines.append(f"## Ignorés ({len(skipped)})")
        for rid, kind, reason in skipped:
            lines.append(f"- `{rid}` ({kind}) : {reason}")
    STATS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Phase 2 -- construction du corpus cat3")
    ap.add_argument("--provider", default=None, help="anthropic|openai|gemini|template")
    ap.add_argument("--sources", default="urdf,pdf",
                    help="urdf,pdf (séparés par des virgules)")
    ap.add_argument("--allow-proprietary-pdf", action="store_true",
                    help="inclure les manuels sans licence conforme (décision explicite)")
    ap.add_argument("--llm-format-pdf", action="store_true",
                    help="passer les manuels par le LLM pour mise en forme (extractif)")
    ap.add_argument("--ocr", action="store_true",
                    help="océriser les PDF scannés (sans couche texte). "
                         "Le texte produit est marqué ocr:true dans le corpus.")
    ap.add_argument("--ocr-max-pages", type=int, default=None,
                    help="borne le nombre de pages océrisées par document")
    args = ap.parse_args()

    report = RunReport("cat3-build-corpus", category=CATEGORY,
                       title="Catégorie 3 — phase 2 (construction du corpus)")

    provider = get_provider(args.provider)
    tc = TokenCounter()
    sources = {s.strip() for s in args.sources.split(",") if s.strip()}
    checker = ContaminationChecker.from_config()

    print(f"Racine projet : {paths.PROJECT_ROOT}")
    print(f"Provider LLM  : {provider.name} | tokenizer : {tc.describe()}")
    print(f"Sources       : {', '.join(sorted(sources))}")
    print(f"Contamination : {checker.describe()}")
    print(f"OCR           : {'activé' if args.ocr else 'désactivé'}\n")

    report.info("Sources", ", ".join(sorted(sources)))
    report.info("Provider LLM", provider.name)
    report.info("Tokenizer", tc.describe())
    report.info("Contamination", checker.describe())
    report.info("OCR", "activé" if args.ocr else "désactivé")
    report.info("--allow-proprietary-pdf", args.allow_proprietary_pdf)

    drafts: list = []
    skipped: list = []
    if "urdf" in sources:
        _iter_urdf(provider, drafts, skipped, report)
    if "pdf" in sources:
        _iter_pdf(provider, drafts, skipped, report,
                  allow_proprietary=args.allow_proprietary_pdf,
                  llm_format=args.llm_format_pdf,
                  use_ocr=args.ocr,
                  ocr_max_pages=args.ocr_max_pages)

    paths.ensure_dirs(CORPUS_PATH.parent)
    rows = []
    n_contaminated = 0
    with CORPUS_PATH.open("w", encoding="utf-8") as f:
        for draft in drafts:
            # Contrôle de contamination : un document qui recoupe le scénario
            # d'évaluation n'entre pas dans le corpus, quelle que soit sa
            # qualité par ailleurs.
            verdict = checker.check(draft.text)
            if verdict.is_contaminated:
                n_contaminated += 1
                reason = f"CONTAMINATION — {verdict.describe()}"
                skipped.append((draft.robot_id, draft.source_type, reason))
                report.skip(draft.robot_id, kind=draft.source_type, reason=reason)
                continue

            rec = assemble_record(draft, category=CATEGORY, token_counter=tc)
            validate_record(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows.append(rec)
            report.ok(draft.robot_id, kind=draft.source_type,
                      detail=f"{rec['n_tokens']} tokens, licence {rec['license']}"
                             + (" [OCR]" if rec.get("ocr") else ""))

    contamination_summary = (
        f"PASSÉ — 0 recoupement sur {len(drafts)} documents examinés "
        f"({checker.describe()})" if n_contaminated == 0 else
        f"{n_contaminated} document(s) exclu(s) sur {len(drafts)} examinés"
    )
    report.info("Résultat contamination", contamination_summary)

    report_path = report.write()
    write_stats(rows, skipped, tc,
                contamination_summary=contamination_summary,
                report_path=report_path)

    by_type = Counter(r["source_type"] for r in rows)
    print(f"\nCorpus écrit : {CORPUS_PATH}")
    print(f"  {len(rows)} enregistrements " +
          " | ".join(f"{t}: {n}" for t, n in sorted(by_type.items())))
    print(f"  contamination : {contamination_summary}")
    if skipped:
        print(f"  {len(skipped)} ignorés (détail dans {STATS_PATH}) :")
        for rid, kind, reason in skipped[:10]:
            print(f"    - {rid} ({kind}) : {reason}")
        if len(skipped) > 10:
            print(f"    ... et {len(skipped) - 10} autres")
    print(f"  rapport : {report_path}")


if __name__ == "__main__":
    main()
