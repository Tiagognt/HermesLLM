# RoboMix full corpus — statistics

- Generated: 2026-07-21T12:42:32.159625+00:00
- Project root: `/home/tiago/HermesPerso/HermesLLM`
- Records: 1202
- Total tokens: 2,421,834 (Qwen3)
- Contamination check: PASSED — 0 overlap over 1202 documents
- Cross-category deduplication: 3 cross-category duplicate(s) removed (MinHash 128 permutations, 16 bands x 8 rows, threshold 0.85)
- Run report: `logs/20260721-124043-merge-corpus.md`

## Mix per category (requirement of the brief)

| Category | Tokens | Share | Target band | Verdict |
|---|---:|---:|---:|---|
| cat1 | 1,648,225 | 68.1 % | 60–70 % | OK |
| cat2 | 518,597 | 21.4 % | 15–25 % | OK |
| cat3 | 255,012 | 10.5 % | 10–15 % | OK |

**Overall mix: COMPLIANT**

## Documents per category

| Category | Documents | Tokens | Mean |
|---|---:|---:|---:|
| cat1 | 966 | 1,648,225 | 1706 |
| cat2 | 163 | 518,597 | 3181 |
| cat3 | 73 | 255,012 | 3493 |
| **total** | **1202** | **2,421,834** | **2014** |

## Per tier
- A: 1,648,225 tokens
- B: 518,597 tokens
- D: 255,012 tokens

## Per license

| License | Documents |
|---|---:|
| Apache-2.0 | 457 |
| CC-BY-4.0 | 360 |
| BSD-3-Clause | 195 |
| MIT | 157 |
| BSD-2-Clause | 20 |
| no-license  <- outside allowlist, inclusion on a recorded decision | 13 |

## Per source nature
- docs: 583 documents
- code: 472 documents
- urdf: 61 documents
- paper: 53 documents
- interfaces: 16 documents
- pdf_manual: 12 documents
- notebooks: 5 documents

## Dropped at merge time

| Reason | Count |
|---|---:|
| cross-category duplicate (exact) | 3 |

## Regeneration

```bash
./rebuild_dataset.sh          # everything, in order
```

The per-category corpora remain the source of truth; this file is a regenerable derivative.
