# Category 3 corpus — statistics

- Generated: 2026-07-21T12:35:17.663562+00:00
- Project root: `/home/tiago/HermesPerso/HermesLLM`
- Records: 73
- Total tokens: 255012 (Qwen3 exact)
- Contamination check: PASSED — 0 overlap over 73 documents examined (3 rules over 1 scenario(s): subway_station_fire)
- Run report: `logs/20260721-123258-cat3-build-corpus.md`

## Per source type
- pdf_manual: 12 records, 84402 tokens (mean 7033)
- urdf: 61 records, 170610 tokens (mean 2796)

## Per license
- Apache-2.0: 18
- BSD-2-Clause: 4
- BSD-3-Clause: 28
- MIT: 10
- no-license: 13  <- outside allowlist, inclusion on an explicit decision

## Extraction quality
- Native extraction: 71
- Text from OCR: 2 (`ocr: true` field, filterable)
  - `cat3-unitree_g1-pdf_manual` — mean confidence 0.977
  - `cat3-unitree_b2-pdf_manual` — mean confidence 0.9813
