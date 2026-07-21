# Corpus catégorie 3 — statistiques

- Généré le : 2026-07-21T10:46:41.925895+00:00
- Racine projet : `/home/tiago/HermesPerso/HermesLLM`
- Enregistrements : 73
- Tokens totaux : 255051 (Qwen3 exact)
- Contrôle de contamination : PASSÉ — 0 recoupement sur 73 documents examinés (3 règles sur 1 scénario(s) : subway_station_fire)
- Rapport d'exécution : `logs/20260721-104427-cat3-build-corpus.md`

## Par type de source
- pdf_manual : 12 enregistrements, 84414 tokens (moyenne 7034)
- urdf : 61 enregistrements, 170637 tokens (moyenne 2797)

## Par licence
- Apache-2.0 : 18
- BSD-2-Clause : 4
- BSD-3-Clause : 28
- MIT : 10
- no-license : 13  ← hors allowlist, inclusion sur décision explicite

## Qualité d'extraction
- Extraction native : 71
- Texte issu d'OCR : 2 (champ `ocr: true`, filtrable)
  - `cat3-unitree_g1-pdf_manual` — confiance moyenne 0.977
  - `cat3-unitree_b2-pdf_manual` — confiance moyenne 0.9813

## Ignorés (1)
- `unitree_h1` (pdf_manual) : ECHEC : h1_manual.pdf n'est pas un PDF : contenu réel détecté = HTML. Le fichier doit être re-téléchargé depuis la source officielle.
