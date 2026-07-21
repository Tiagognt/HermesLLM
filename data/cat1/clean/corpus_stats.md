# Category 1 corpus — statistics

- Generated: 2026-07-21T12:39:47.109896+00:00
- Project root: `/home/tiago/HermesPerso/HermesLLM`
- Tier: A
- Records: 966
- Total tokens: 1648225 (Qwen3 exact)
- Contamination check: PASSED — 0 overlap (3 rules over 1 scenario(s): subway_station_fire)
- Deduplication: 25 exact duplicates, 39 near-duplicates removed (MinHash 128 permutations, 16 bands x 8 rows, threshold 0.85)
- Run report: `logs/20260721-123518-cat1-build-corpus.md`

## Per source family

| Family | Documents | Tokens | Share |
|---|---:|---:|---:|
| ros_docs | 357 | 644,844 | 39.1 % |
| sim_docs | 187 | 429,517 | 26.1 % |
| examples | 266 | 233,982 | 14.2 % |
| algorithms | 100 | 214,190 | 13.0 % |
| planning_code | 40 | 79,384 | 4.8 % |
| interfaces | 16 | 46,308 | 2.8 % |

## Per source

| Source | Family | Kept | Tokens | Cap | Dropped (quota) |
|---|---|---:|---:|---:|---:|
| `ros2_documentation` | ros_docs | 178 | 300,097 | 300,000 | 193 |
| `nav2_docs` | ros_docs | 70 | 141,934 | 140,000 | 204 |
| `gazebo_docs` | sim_docs | 59 | 116,822 | 120,000 | 0 |
| `ros2_design` | ros_docs | 33 | 92,480 | 90,000 | 28 |
| `moveit2_tutorials` | ros_docs | 60 | 91,001 | 90,000 | 15 |
| `mujoco_docs` | sim_docs | 24 | 90,660 | 90,000 | 48 |
| `webots_docs` | sim_docs | 43 | 81,736 | 80,000 | 209 |
| `python_robotics` | algorithms | 35 | 80,752 | 80,000 | 169 |
| `px4_user_guide` | sim_docs | 34 | 73,102 | 70,000 | 828 |
| `drake_docs` | sim_docs | 27 | 67,197 | 60,000 | 108 |
| `ros2_demos` | examples | 53 | 61,629 | 60,000 | 91 |
| `ros2_examples` | examples | 91 | 50,272 | 50,000 | 17 |
| `ompl` | algorithms | 24 | 47,627 | 45,000 | 101 |
| `py_trees` | examples | 24 | 46,330 | 45,000 | 45 |
| `unified_planning` | planning_code | 29 | 36,288 | 50,000 | 0 |
| `pinocchio` | algorithms | 16 | 35,824 | 35,000 | 65 |
| `code_as_policies` | planning_code | 5 | 30,873 | 30,000 | 7 |
| `ros2_controllers` | examples | 38 | 30,446 | 40,000 | 0 |
| `modern_robotics` | algorithms | 8 | 29,661 | 35,000 | 0 |
| `moveit_task_constructor` | examples | 28 | 23,795 | 40,000 | 0 |
| `behaviortree_cpp` | examples | 32 | 21,510 | 35,000 | 0 |
| `robotics_toolbox` | algorithms | 17 | 20,326 | 50,000 | 0 |
| `common_interfaces` | interfaces | 10 | 19,843 | 40,000 | 0 |
| `ros2_control_docs` | ros_docs | 16 | 19,332 | 40,000 | 0 |
| `virtualhome` | planning_code | 6 | 12,223 | 40,000 | 0 |
| `moveit_msgs` | interfaces | 3 | 10,954 | 25,000 | 0 |
| `control_msgs` | interfaces | 1 | 8,415 | 20,000 | 0 |
| `nav2_msgs` | interfaces | 2 | 7,096 | 25,000 | 0 |

## Per content nature
- code: 401 documents
- docs: 544 documents
- interfaces: 16 documents
- notebooks: 5 documents

## Per license
- Apache-2.0: 414
- BSD-2-Clause: 16
- BSD-3-Clause: 167
- CC-BY-4.0: 271
- MIT: 98

## Dropped documents

| Reason | Count |
|---|---:|
| over quota | 2128 |
| near duplicate | 39 |
| exact duplicate | 25 |

## Masked secrets
- no secret detected in the retained sources
