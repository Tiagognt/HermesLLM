#!/usr/bin/env bash
#
# Rebuild the complete RoboMix DAPT dataset, end to end.
#
#   ./rebuild_dataset.sh                 # collect + build + merge (everything)
#   ./rebuild_dataset.sh --build-only    # skip phase 1, rebuild from raw files
#   ./rebuild_dataset.sh --collect-only  # phase 1 only
#   ./rebuild_dataset.sh --refresh       # re-clone instead of using the cache
#
# Phase 1 needs network access and git; phase 2 and the merge run fully
# offline (the Qwen3 tokenizer is the only thing that may reach out to
# Hugging Face, and it degrades gracefully to an approximate count).
#
# Expect roughly 20-40 min for a full run from an empty cache, dominated by
# cloning ~34 repositories and by the OCR of two scanned manuals. A
# --build-only run takes a few minutes.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Use the project virtualenv when it exists, otherwise the system python.
if [[ -x "$ROOT/.env/bin/python" ]]; then
  PY="$ROOT/.env/bin/python"
else
  PY="$(command -v python3)"
fi

DO_COLLECT=1
DO_BUILD=1
REFRESH=""

for arg in "$@"; do
  case "$arg" in
    --build-only)   DO_COLLECT=0 ;;
    --collect-only) DO_BUILD=0 ;;
    --refresh)      REFRESH="--refresh" ;;
    -h|--help)      sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

step() { printf '\n\033[1m=== %s ===\033[0m\n' "$1"; }

START=$SECONDS

if [[ $DO_COLLECT -eq 1 ]]; then
  step "PHASE 1/3 — collection (network + git required)"
  step "cat3: robot URDFs"
  "$PY" src/cat3/collect_pilot.py
  step "cat1: general robotics documentation and code"
  "$PY" src/cat1/collect_docs.py $REFRESH
  step "cat2: HMRS repositories and arXiv papers"
  "$PY" src/cat2/collect_hmrs.py $REFRESH
fi

if [[ $DO_BUILD -eq 1 ]]; then
  step "PHASE 2/3 — corpus build (offline)"
  step "cat3: URDF + OCR'd manuals"
  "$PY" src/cat3/build_corpus.py --sources urdf,pdf --ocr
  step "cat1"
  "$PY" src/cat1/build_corpus.py
  step "cat2"
  "$PY" src/cat2/build_corpus.py

  step "PHASE 3/3 — merge and mix verification"
  # merge_corpus.py exits non-zero when a mix band is violated: `set -e`
  # therefore stops the script, which is the intended behaviour.
  "$PY" src/common/merge_corpus.py

  step "Final independent contamination audit"
  "$PY" src/common/contamination.py
fi

printf '\n\033[1mDone in %d min %d s.\033[0m\n' $(((SECONDS-START)/60)) $(((SECONDS-START)%60))
if [[ $DO_BUILD -eq 1 ]]; then
  echo "Deliverable : data/full/corpus_full.jsonl"
  echo "Statistics  : data/full/corpus_full_stats.md"
  echo "Run reports : logs/"
fi
