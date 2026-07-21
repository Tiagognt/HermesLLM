# Category 2 corpus — statistics

- Generated: 2026-07-21T12:40:43.409648+00:00
- Project root: `/home/tiago/HermesPerso/HermesLLM`
- Tier: B
- Records: 166
- Total tokens: 519185 (Qwen3 exact)
- Contamination check: PASSED — 0 overlap (3 rules over 1 scenario(s): subway_station_fire)
- Deduplication: 0 exact duplicates, 1 near-duplicates removed (MinHash 128 permutations, 16 bands x 8 rows, threshold 0.85)
- Run report: `logs/20260721-123947-cat2-build-corpus.md`

## Per source family

| Family | Documents | Tokens | Share |
|---|---:|---:|---:|
| papers | 53 | 282,046 | 54.3 % |
| hmrs_framework | 49 | 120,062 | 23.1 % |
| hmrs_book | 36 | 75,770 | 14.6 % |
| fleet | 28 | 41,307 | 8.0 % |

## Per source (the 43 papers are grouped)

| Source | Family | Kept | Tokens | Cap | Dropped (quota) |
|---|---|---:|---:|---:|---:|
| `43 arXiv papers` | papers | 53 | 282,046 | 280,000 | 44 |
| `ros2_multirobot_book` | hmrs_book | 36 | 75,770 | 75,000 | 5 |
| `partnr` | hmrs_framework | 22 | 54,373 | 50,000 | 119 |
| `roco` | hmrs_framework | 15 | 47,101 | 45,000 | 9 |
| `rmf_demos` | fleet | 25 | 35,609 | 35,000 | 13 |
| `emos` | hmrs_framework | 12 | 18,588 | 35,000 | 0 |
| `open_rmf` | fleet | 3 | 5,698 | 40,000 | 0 |

## Per content nature
- code: 74 documents
- docs: 39 documents
- paper: 53 documents

## Per license
- Apache-2.0: 28
- CC-BY-4.0: 89
- MIT: 49

## Dropped documents

| Reason | Count |
|---|---:|
| over quota | 190 |
| near duplicate | 1 |

## Masked secrets
- no secret detected in the retained sources
