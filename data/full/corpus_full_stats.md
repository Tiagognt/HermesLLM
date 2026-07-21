# Corpus complet RoboMix — statistiques

- Généré le : 2026-07-21T11:27:15.631099+00:00
- Racine projet : `/home/tiago/HermesPerso/HermesLLM`
- Enregistrements : 1202
- Tokens totaux : 2,421,873 (Qwen3)
- Contrôle de contamination : PASSÉ — 0 recoupement sur 1202 documents
- Déduplication croisée : 3 doublon(s) inter-catégories retiré(s) (MinHash 128 permutations, 16 bandes x 8 lignes, seuil 0.85)
- Rapport d'exécution : `logs/20260721-112527-merge-corpus.md`

## Mélange par catégorie (exigence des consignes)

| Catégorie | Tokens | Part | Bande visée | Verdict |
|---|---:|---:|---:|---|
| cat1 | 1,648,225 | 68.1 % | 60–70 % | OK |
| cat2 | 518,597 | 21.4 % | 15–25 % | OK |
| cat3 | 255,051 | 10.5 % | 10–15 % | OK |

**Mélange global : CONFORME**

## Documents par catégorie

| Catégorie | Documents | Tokens | Moyenne |
|---|---:|---:|---:|
| cat1 | 966 | 1,648,225 | 1706 |
| cat2 | 163 | 518,597 | 3181 |
| cat3 | 73 | 255,051 | 3493 |
| **total** | **1202** | **2,421,873** | **2014** |

## Par tier
- A : 1,648,225 tokens
- B : 518,597 tokens
- D : 255,051 tokens

## Par licence

| Licence | Documents |
|---|---:|
| Apache-2.0 | 457 |
| CC-BY-4.0 | 360 |
| BSD-3-Clause | 195 |
| MIT | 157 |
| BSD-2-Clause | 20 |
| no-license  ← hors allowlist, inclusion sur décision tracée | 13 |

## Par nature de source
- docs : 583 documents
- code : 472 documents
- urdf : 61 documents
- paper : 53 documents
- interfaces : 16 documents
- pdf_manual : 12 documents
- notebooks : 5 documents

## Écartés à la fusion

| Motif | Nombre |
|---|---:|
| doublon inter-catégories (exact) | 3 |

## Régénération

```bash
python3 src/cat1/build_corpus.py
python3 src/cat2/build_corpus.py
python3 src/cat3/build_corpus.py --sources urdf,pdf --ocr
python3 src/common/merge_corpus.py
```

Les corpus par catégorie restent la source de vérité ; ce fichier en est un dérivé régénérable.
