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
from common.license_utils import classify_license, is_collectible
from common.llm_provider import get_provider
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

def _iter_urdf(provider, drafts: list, skipped: list) -> None:
    if not METADATA_PATH.exists():
        print(f"  [urdf] aucun fichier de métadonnées : {METADATA_PATH}")
        print("         -> lancez d'abord collect_pilot.py")
        return

    for line in METADATA_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        meta = json.loads(line)
        rid = meta["robot_id"]
        status = meta["license_status"]

        if not is_collectible(status, allow_no_license_override=rid in ALLOW_NO_LICENSE_FOR):
            skipped.append((rid, "urdf", f"licence non conforme ({status})"))
            continue

        urdf_path = paths.from_relative(meta["raw_urdf_path"])
        if not urdf_path.exists():
            skipped.append((rid, "urdf", f"fichier absent : {urdf_path}"))
            continue

        try:
            drafts.append(urdf_adapter.adapt(
                rid, urdf_path,
                license_status=status,
                url=meta.get("repo_url", ""),
                source_name=meta.get("source_type", "robot_descriptions"),
                provider=provider,
            ))
        except Exception as exc:  # un URDF cassé n'arrête pas le run
            skipped.append((rid, "urdf", f"ECHEC : {exc}"))


# --------------------------------------------------------------------------
# Voie PDF
# --------------------------------------------------------------------------

def _iter_pdf(provider, drafts: list, skipped: list, *,
              allow_proprietary: bool, llm_format: bool) -> None:
    manifest_path = _resolve_manifest()
    if manifest_path is None:
        print(f"  [pdf] manifeste introuvable. Attendu : {MANIFEST_PATH}")
        return

    manuals = json.loads(manifest_path.read_text(encoding="utf-8"))["manuals"]
    print(f"  [pdf] manifeste : {manifest_path} ({len(manuals)} entrées)")
    print(f"  [pdf] dossier des manuels : {MANUALS_DIR}")

    for m in manuals:
        rid = m["robot_id"]
        robot_dir = MANUALS_DIR / rid
        pdf_path = pdf_adapter.find_pdf(robot_dir, m.get("target_filename"))

        if pdf_path is None:
            skipped.append((rid, "pdf_manual", f"aucun .pdf dans {robot_dir}"))
            continue

        status = classify_license(m.get("license_spdx"))
        # Décision par robot dans le manifeste, ou globale via l'option CLI.
        override = bool(m.get("allow_no_license", False)) or allow_proprietary
        if not is_collectible(status, allow_no_license_override=override):
            skipped.append((rid, "pdf_manual",
                            f"licence non conforme ({status}) -- utilisez "
                            f"--allow-proprietary-pdf ou allow_no_license dans le manifeste"))
            continue

        try:
            drafts.append(pdf_adapter.adapt(
                rid, pdf_path,
                license_status=status,
                url=m.get("url", ""),
                source_name=f"manual:{rid}",
                provider=provider,
                use_llm_format=llm_format,
            ))
            print(f"  [pdf] {rid} <- {pdf_path.name}")
        except Exception as exc:  # PDF corrompu / scanné -> journalisé, on continue
            skipped.append((rid, "pdf_manual", f"ECHEC : {exc}"))


# --------------------------------------------------------------------------
# Statistiques
# --------------------------------------------------------------------------

def write_stats(rows: list, skipped: list, tc: TokenCounter) -> None:
    by_type = Counter(r["source_type"] for r in rows)
    tokens_by_type: Counter = Counter()
    for r in rows:
        tokens_by_type[r["source_type"]] += r["n_tokens"]
    total_tokens = sum(r["n_tokens"] for r in rows)

    lines = ["# Corpus catégorie 3 — statistiques", ""]
    lines.append(f"- Généré le : {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Racine projet : `{paths.PROJECT_ROOT}`")
    lines.append(f"- Enregistrements : {len(rows)}")
    lines.append(f"- Tokens totaux : {total_tokens} "
                 f"({'Qwen3 exact' if tc.is_exact else 'APPROXIMATIF — ' + tc.describe()})")
    lines.append("")
    lines.append("## Par type de source")
    for t in sorted(by_type):
        n = by_type[t]
        moy = tokens_by_type[t] // n if n else 0
        lines.append(f"- {t} : {n} enregistrements, {tokens_by_type[t]} tokens "
                     f"(moyenne {moy})")
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
    args = ap.parse_args()

    provider = get_provider(args.provider)
    tc = TokenCounter()
    sources = {s.strip() for s in args.sources.split(",") if s.strip()}

    print(f"Racine projet : {paths.PROJECT_ROOT}")
    print(f"Provider LLM  : {provider.name} | tokenizer : {tc.describe()}")
    print(f"Sources       : {', '.join(sorted(sources))}\n")

    drafts: list = []
    skipped: list = []
    if "urdf" in sources:
        _iter_urdf(provider, drafts, skipped)
    if "pdf" in sources:
        _iter_pdf(provider, drafts, skipped,
                  allow_proprietary=args.allow_proprietary_pdf,
                  llm_format=args.llm_format_pdf)

    paths.ensure_dirs(CORPUS_PATH.parent)
    rows = []
    with CORPUS_PATH.open("w", encoding="utf-8") as f:
        for draft in drafts:
            rec = assemble_record(draft, category=CATEGORY, token_counter=tc)
            validate_record(rec)
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows.append(rec)

    write_stats(rows, skipped, tc)

    by_type = Counter(r["source_type"] for r in rows)
    print(f"\nCorpus écrit : {CORPUS_PATH}")
    print(f"  {len(rows)} enregistrements " +
          " | ".join(f"{t}: {n}" for t, n in sorted(by_type.items())))
    if skipped:
        print(f"  {len(skipped)} ignorés (détail dans {STATS_PATH}) :")
        for rid, kind, reason in skipped[:10]:
            print(f"    - {rid} ({kind}) : {reason}")
        if len(skipped) > 10:
            print(f"    ... et {len(skipped) - 10} autres")


if __name__ == "__main__":
    main()
