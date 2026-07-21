# Rollback guide

The dataset was built in three stages, each preceded by a git tag. Every
stage can be undone independently, and the corpus can be resized without
re-collecting anything.

| Tag | State it points at |
|---|---|
| `pre-cat3-close` | before the cat3 closing work (OCR, fetch/tiago fixes, run reports, contamination) |
| `pre-cat1` | before the category-1 pilot |
| `pre-cat2` | before category 2, the merged corpus, and the extra cat1/cat3 sources |

```bash
git tag -l                       # list them
git diff --stat pre-cat2..HEAD   # what changed since a given stage
```

The git clone caches (`data/*/raw/_cache/`, ~6.6 GB) are **not tracked**:
they are fully regenerable by phase 1 from the commits pinned in
`collection_metadata.jsonl`, so no reset ever touches them. Delete them by
hand if you want the space back.

---

## Undo everything, back to before the dataset work

```bash
cd /home/tiago/HermesPerso/HermesLLM
git reset --hard pre-cat3-close
git clean -fd data/cat1 data/cat2 data/full logs/
rm -rf data/*/raw/_cache
```

## Undo one stage

```bash
git reset --hard pre-cat2   # keeps cat1 and cat3, drops cat2 + the merge
git reset --hard pre-cat1   # keeps cat3 only
```

Non-destructive variant, which keeps the history and adds a revert commit:

```bash
git revert --no-commit pre-cat2..HEAD && git commit -m "revert: dataset work"
```

---

## Undo one piece

| What you want to remove | How |
|---|---|
| All of category 2 | `rm -rf src/cat2 data/cat2`, then re-run `merge_corpus.py` (it skips a missing category and says so) |
| The research papers only | empty `PAPER_CATALOG` in `src/cat2/sources.py`, re-run both cat2 phases |
| The 10 robots added to cat3 | `git checkout pre-cat2 -- src/cat3/sources.py`, re-run both cat3 phases |
| The 3 sources added to cat1 | `git checkout pre-cat2 -- src/cat1/sources.py`, re-run both cat1 phases |
| The merged corpus | `rm -rf data/full` — the per-category corpora are untouched, they are the source of truth |
| The vendor manuals | set `allow_no_license` to `false` in `src/cat3/pdf_manifest.json`, re-run cat3 phase 2. The manuals leave the corpus and are logged as set aside |
| OCR | `git checkout pre-cat3-close -- src/cat3/pdf_adapter.py src/common/corpus_assembler.py`, delete `src/common/ocr.py` |
| The contamination check | `git checkout pre-cat3-close -- src/cat3/build_corpus.py`, delete `src/common/contamination*.{py,json}` |
| The run reports | `git checkout pre-cat3-close -- src/cat3/collect_pilot.py`, delete `src/common/run_report.py` |

After any partial rollback, rebuild:

```bash
./rebuild_dataset.sh --build-only
```

---

## Rebalance the mix without re-collecting

This is the intended lever, not a workaround. `merge_corpus.py` exits
non-zero when a band is violated; `--budget-scale` is how you fix it.

```bash
python3 src/cat1/build_corpus.py --budget-scale 0.85   # smaller cat1
python3 src/cat2/build_corpus.py --budget-scale 1.10   # larger cat2
python3 src/common/merge_corpus.py
```

For per-source tuning, edit `token_budget` in the relevant `sources.py` and
re-run phase 2 only. Phase 1 is never replayed: the raw files and the
downloaded papers stay on disk.

---

## Restore the original dependency set

Only one optional package was added:

```bash
pip uninstall rapidocr-onnxruntime
```

OCR then becomes unavailable; `--ocr` fails with an explicit message rather
than silently, and phase 2 without `--ocr` behaves exactly as before.
