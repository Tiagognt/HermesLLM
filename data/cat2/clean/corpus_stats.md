# Corpus catégorie 2 — statistiques

- Généré le : 2026-07-21T11:19:03.259112+00:00
- Racine projet : `/home/tiago/HermesPerso/HermesLLM`
- Tier : B
- Enregistrements : 166
- Tokens totaux : 519185 (Qwen3 exact)
- Contrôle de contamination : PASSÉ — 0 recoupement (3 règles sur 1 scénario(s) : subway_station_fire)
- Déduplication : 0 doublons exacts, 1 quasi-doublons retirés (MinHash 128 permutations, 16 bandes x 8 lignes, seuil 0.85)
- Rapport d'exécution : `logs/20260721-111807-cat2-build-corpus.md`

## Par famille de sources

| Famille | Documents | Tokens | Part |
|---|---:|---:|---:|
| papers | 53 | 282,046 | 54.3 % |
| hmrs_framework | 49 | 120,062 | 23.1 % |
| hmrs_book | 36 | 75,770 | 14.6 % |
| fleet | 28 | 41,307 | 8.0 % |

## Par source (les 43 articles sont regroupés)

| Source | Famille | Retenus | Tokens | Plafond | Écartés (quota) |
|---|---|---:|---:|---:|---:|
| `43 articles arXiv` | papers | 53 | 282,046 | 280,000 | 44 |
| `ros2_multirobot_book` | hmrs_book | 36 | 75,770 | 75,000 | 5 |
| `partnr` | hmrs_framework | 22 | 54,373 | 50,000 | 119 |
| `roco` | hmrs_framework | 15 | 47,101 | 45,000 | 9 |
| `rmf_demos` | fleet | 25 | 35,609 | 35,000 | 13 |
| `emos` | hmrs_framework | 12 | 18,588 | 35,000 | 0 |
| `open_rmf` | fleet | 3 | 5,698 | 40,000 | 0 |

## Par nature de contenu
- code : 74 documents
- docs : 39 documents
- paper : 53 documents

## Par licence
- Apache-2.0 : 28
- CC-BY-4.0 : 89
- MIT : 49

## Documents écartés

| Motif | Nombre |
|---|---:|
| hors quota | 190 |
| doublon near | 1 |

## Secrets masqués
- aucun secret détecté dans les sources retenues
