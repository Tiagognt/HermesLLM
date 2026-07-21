# Corpus catégorie 3 — statistiques

- Généré le : 2026-07-21T08:17:33.048580+00:00
- Racine projet : `/home/tiago/HermesPerso/HermesLLM`
- Enregistrements : 63
- Tokens totaux : 236604 (Qwen3 exact)
- Contrôle de contamination : PASSÉ — 0 recoupement sur 63 documents examinés (3 règles sur 1 scénario(s) : subway_station_fire)
- Rapport d'exécution : `logs/20260721-081519-cat3-build-corpus.md`

## Par type de source
- pdf_manual : 12 enregistrements, 84414 tokens (moyenne 7034)
- urdf : 51 enregistrements, 152190 tokens (moyenne 2984)

## Par licence
- Apache-2.0 : 12
- BSD-2-Clause : 3
- BSD-3-Clause : 26
- MIT : 9
- no-license : 13  ← hors allowlist, inclusion sur décision explicite

## Qualité d'extraction
- Extraction native : 61
- Texte issu d'OCR : 2 (champ `ocr: true`, filtrable)
  - `cat3-unitree_g1-pdf_manual` — confiance moyenne 0.977
  - `cat3-unitree_b2-pdf_manual` — confiance moyenne 0.9813

## Ignorés (1)
- `unitree_h1` (pdf_manual) : ECHEC : h1_manual.pdf n'est pas un PDF : contenu réel détecté = HTML. Le fichier doit être re-téléchargé depuis la source officielle.
