# Retour arrière — clôture de cat3 (2026-07-21)

Point de restauration : **tag git `pre-cat3-close`** = commit `ff88197`
(« cat3 almost finish, just need the use of an OCR for specific PDF »).

Ce tag pointe sur l'état exact du projet *avant* les travaux de clôture de
cat3. Les données (`data/`) sont suivies par git, donc le corpus, les
métadonnées et les manuels sont couverts par le retour arrière au même
titre que le code.

## Tout annuler

```bash
cd /home/tiago/HermesPerso/HermesLLM
git reset --hard pre-cat3-close
git clean -fd logs/ ROLLBACK.md          # retire les fichiers non suivis créés depuis
```

Variante non destructive (garde l'historique, crée un commit d'annulation) :

```bash
git revert --no-commit pre-cat3-close..HEAD && git commit -m "revert: clôture cat3"
```

## Comparer avant / après

```bash
git diff --stat pre-cat3-close..HEAD          # tous les fichiers touchés
git diff pre-cat3-close..HEAD -- src/         # seulement le code
git show pre-cat3-close:data/cat3/clean/corpus_stats.md   # anciennes stats
```

## Annuler seulement une partie

| Ce que vous voulez retirer | Commande |
|---|---|
| La mise à jour de `CLAUDE.md` | `git checkout pre-cat3-close -- CLAUDE.md` |
| Le nouveau `README.md` | `git checkout pre-cat3-close -- README.md` |
| Le contrôle de contamination | `git checkout pre-cat3-close -- src/cat3/build_corpus.py` puis supprimer `src/common/contamination*.{py,json}` |
| L'OCR | `git checkout pre-cat3-close -- src/cat3/pdf_adapter.py src/common/corpus_assembler.py` puis supprimer `src/common/ocr.py` |
| Les rapports d'exécution | `git checkout pre-cat3-close -- src/cat3/collect_pilot.py` puis supprimer `src/common/run_report.py` |
| Le correctif `fetch` (namespaces XML) | `git checkout pre-cat3-close -- src/cat3/urdf_parser.py` |
| Le correctif `tiago` | `git checkout pre-cat3-close -- src/cat3/sources.py` |

Après toute annulation partielle, régénérer le corpus :

```bash
python3 src/cat3/build_corpus.py --sources urdf,pdf --ocr
```

## Annuler uniquement la décision sur les manuels PDF

Sans toucher au code : passer `allow_no_license` à `false` sur les entrées
concernées dans `src/cat3/pdf_manifest.json`, puis relancer la phase 2. Les
12 manuels sortent du corpus et sont journalisés comme écartés (le corpus
retombe à 51 enregistrements URDF).

## Rétablir l'état d'origine des dépendances

Le seul paquet ajouté est optionnel :

```bash
pip uninstall rapidocr-onnxruntime
```

L'OCR devient alors indisponible ; `--ocr` échoue avec un message explicite
plutôt que silencieusement, et la phase 2 sans `--ocr` fonctionne comme
avant.
