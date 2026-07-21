# Corpus catégorie 1 — statistiques

- Généré le : 2026-07-21T09:18:40.445754+00:00
- Racine projet : `/home/tiago/HermesPerso/HermesLLM`
- Tier : A
- Enregistrements : 876
- Tokens totaux : 1507283 (Qwen3 exact)
- Contrôle de contamination : PASSÉ — 0 recoupement (3 règles sur 1 scénario(s) : subway_station_fire)
- Déduplication : 23 doublons exacts, 34 quasi-doublons retirés (MinHash 128 permutations, 16 bandes x 8 lignes, seuil 0.85)
- Rapport d'exécution : `logs/20260721-091520-cat1-build-corpus.md`

## Par famille de sources

| Famille | Documents | Tokens | Part |
|---|---:|---:|---:|
| ros_docs | 357 | 644,844 | 42.8 % |
| sim_docs | 153 | 356,415 | 23.6 % |
| algorithms | 100 | 214,190 | 14.2 % |
| examples | 210 | 166,142 | 11.0 % |
| planning_code | 40 | 79,384 | 5.3 % |
| interfaces | 16 | 46,308 | 3.1 % |

## Par source

| Source | Famille | Retenus | Tokens | Plafond | Écartés (quota) |
|---|---|---:|---:|---:|---:|
| `ros2_documentation` | ros_docs | 178 | 300,097 | 300,000 | 193 |
| `nav2_docs` | ros_docs | 70 | 141,934 | 140,000 | 204 |
| `gazebo_docs` | sim_docs | 59 | 116,822 | 120,000 | 0 |
| `ros2_design` | ros_docs | 33 | 92,480 | 90,000 | 28 |
| `moveit2_tutorials` | ros_docs | 60 | 91,001 | 90,000 | 15 |
| `mujoco_docs` | sim_docs | 24 | 90,660 | 90,000 | 48 |
| `webots_docs` | sim_docs | 43 | 81,736 | 80,000 | 209 |
| `python_robotics` | algorithms | 35 | 80,752 | 80,000 | 169 |
| `drake_docs` | sim_docs | 27 | 67,197 | 60,000 | 108 |
| `ros2_demos` | examples | 53 | 61,629 | 60,000 | 91 |
| `ros2_examples` | examples | 91 | 50,272 | 50,000 | 17 |
| `ompl` | algorithms | 24 | 47,627 | 45,000 | 101 |
| `unified_planning` | planning_code | 29 | 36,288 | 50,000 | 0 |
| `pinocchio` | algorithms | 16 | 35,824 | 35,000 | 65 |
| `code_as_policies` | planning_code | 5 | 30,873 | 30,000 | 7 |
| `ros2_controllers` | examples | 38 | 30,446 | 40,000 | 0 |
| `modern_robotics` | algorithms | 8 | 29,661 | 35,000 | 0 |
| `moveit_task_constructor` | examples | 28 | 23,795 | 40,000 | 0 |
| `robotics_toolbox` | algorithms | 17 | 20,326 | 50,000 | 0 |
| `common_interfaces` | interfaces | 10 | 19,843 | 40,000 | 0 |
| `ros2_control_docs` | ros_docs | 16 | 19,332 | 40,000 | 0 |
| `virtualhome` | planning_code | 6 | 12,223 | 40,000 | 0 |
| `moveit_msgs` | interfaces | 3 | 10,954 | 25,000 | 0 |
| `control_msgs` | interfaces | 1 | 8,415 | 20,000 | 0 |
| `nav2_msgs` | interfaces | 2 | 7,096 | 25,000 | 0 |

## Par nature de contenu
- code : 345 documents
- docs : 510 documents
- interfaces : 16 documents
- notebooks : 5 documents

## Par licence
- Apache-2.0 : 414
- BSD-2-Clause : 16
- BSD-3-Clause : 143
- CC-BY-4.0 : 237
- MIT : 66

## Documents écartés

| Motif | Nombre |
|---|---:|
| hors quota | 1255 |
| doublon near | 34 |
| doublon exact | 23 |

## Secrets masqués
- aucun secret détecté dans les sources retenues
