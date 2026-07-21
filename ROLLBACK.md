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

---

# Retour arrière — pilote catégorie 1 (2026-07-21)

Point de restauration : **tag git `pre-cat1`** = commit `4522b38`
(clôture de cat3). Il précède tout le travail sur cat1.

## Tout annuler

```bash
cd /home/tiago/HermesPerso/HermesLLM
git reset --hard pre-cat1
git clean -fd data/cat1 logs/          # retire les bruts et rapports cat1
```

Le cache des clones git (`data/*/raw/_cache/`, 5,6 Go pour cat1) n'est plus
suivi par git depuis ce commit : il n'est donc pas concerné par le reset.
Pour le supprimer aussi : `rm -rf data/cat1/raw/_cache`.

## Annuler seulement une partie

| Ce que vous voulez retirer | Commande |
|---|---|
| Toute la catégorie 1 | `git rm -r --cached src/cat1 data/cat1 && rm -rf src/cat1 data/cat1` |
| La déduplication | `git checkout pre-cat1 -- src/common/` puis retirer les appels dans `src/cat1/build_corpus.py` |
| Le scrubbing de secrets | idem, module `src/common/secret_scrubber.py` |
| Le point d'extension `extra=` du schéma | `git checkout pre-cat1 -- src/common/corpus_assembler.py` (casse cat1, pas cat3) |
| La mise à jour du README | `git checkout pre-cat1 -- README.md` |
| Le détachement du cache git du suivi | `git checkout pre-cat1 -- .gitignore` puis `git add data/cat3/raw/_cache` |

## Changer la taille de cat1 sans rien recollecter

C'est le levier prévu, pas un contournement :

```bash
python3 src/cat1/build_corpus.py --budget-scale 0.75   # ~1,13 M tokens
python3 src/cat1/build_corpus.py --budget-scale 1.20   # ~1,80 M tokens
```

Pour un réglage par source, modifier `token_budget` dans
`src/cat1/sources.py` et relancer la phase 2. La phase 1 n'est jamais
rejouée.

## Retirer une source précise du corpus

Supprimer (ou commenter) son entrée dans `src/cat1/sources.py`, puis :

```bash
python3 src/cat1/collect_docs.py     # réécrit les métadonnées
python3 src/cat1/build_corpus.py
```
