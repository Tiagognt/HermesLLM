# Motivation du projet

Je souhaite créer un data-set pour réaliser un entrainement DAPT d'un LLM open source (un model de la famille qwen3.5).
Le LLM qui sera entrainé par mon collegue aura une architecture MoE (Mixture of Expert). Il a pour but de commander une équipe de robots hétérogènes (aux capacités différentes: robot mobile sur roues, robot chien, robot humanoïde, et peut être un bras manipulateur et un drone).
Le LLM doit prendre des instructions en language naturel comme "go save this man" et ensuite il doit établir une planification des taches, des commandes de contrôle pour les différents robots, etc ...
---

# Consignes pour le projet

Dans ce projet, il y a le dossier doc/ qui contient des fichiers pdf qui servent d'indication. Ils ne sont pas à prendre au pied de la lettre donc il ne faut pas que tu t'enferme dans une direction de pensée en les lisant.
Si je veux que tu traite un document comme une vérité absolue je te le ferais savoir

Lorsque je te demande de réaliser une tache pour moi je veux que tu m'explique sous forme d'un rapport structuré, toutes les étapes que tu as réalisé, toutes les choses qui t'ont bloqués et autres détails si nécessaires.

## Contexte projet

Construction d'un corpus d'entraînement pour un LLM orienté robotique.
Le corpus est découpé en catégories ; **cat3 (URDF & Robot Specs)** est la
seule implémentée à ce jour. cat1 et cat2 viendront ensuite et
réutiliseront `src/common/` sans modification.

Chaîne en deux phases volontairement séparées :

- **Phase 1 — collecte** (`collect_pilot.py`) : récupère des fichiers
  bruts + métadonnées de provenance/licence. Ne transforme rien.
- **Phase 2 — transformation** (`build_corpus.py`) : produit
  `corpus_clean.jsonl` + `corpus_stats.md`.

Les deux phases ont des cycles de vie indépendants : on doit pouvoir
régénérer les descriptions **sans re-collecter**. Ne jamais les fusionner.

---

## Préférences de travail de l'utilisateur

- **Répondre en français.**
- À la fin d'une tâche, fournir un **rapport structuré** : étapes
  réalisées, blocages rencontrés, décisions prises, ce qui reste ouvert.
- Les PDF déposés dans le projet (`Consignes_création_dataset.pdf`, etc.)
  sont **indicatifs, pas parole d'évangile**. Ne pas s'y enfermer. Si un
  document doit être traité comme vérité absolue, l'utilisateur le dira
  explicitement.
- Vérifier empiriquement plutôt qu'affirmer : ce projet a déjà eu
  plusieurs bugs invisibles à la lecture et trouvés uniquement en
  exécutant le code.

---

## Règles techniques non négociables

### 1. Aucun chiffre halluciné dans le corpus

Tout nombre du corpus vient du parsing déterministe (`urdf_parser.py`),
jamais d'un LLM. `llm_provider.verify_numbers()` vérifie chaque nombre du
texte généré contre les grandeurs extraites ; en cas d'échec, on retombe
sur la description gabarit déterministe. **Ne jamais contourner ce
garde-fou.**

### 2. Barrière licence

Allowlist (`license_utils.py`) : MIT / BSD-x-Clause / Apache-2.0 /
CC-BY-x.x. Tout le reste est `flagged:*` et jamais collecté
automatiquement. `no-license` n'est collecté que sur décision **explicite
et tracée** (`ALLOW_NO_LICENSE_FOR`, ou `allow_no_license` dans
`pdf_manifest.json`).

Ne jamais élargir l'allowlist sans demander. Ne jamais forcer l'inclusion
d'un contenu propriétaire de sa propre initiative. Exeption pour les fichiers pdfs téléchargés manuellement par l'utilisateur.

### 3. Chemins

Tous les chemins passent par `src/common/paths.py`. **Aucun chemin
relatif** du type `../../data/` dans le code : les scripts doivent se
lancer depuis n'importe quel répertoire. Racine auto-détectée,
surchargeable par `HERMES_ROOT`.

Les chemins **stockés** dans les JSONL sont relatifs à la racine
(`paths.to_relative()` / `paths.from_relative()`), pour que le projet
reste déplaçable.

### 4. Aucun saut silencieux

Un élément ignoré (fichier absent, licence non conforme, extraction
vide) doit être **journalisé avec sa raison** et compté dans le rapport
final. Un `continue` muet est un bug — c'est exactement ce qui a masqué
l'échec total de la voie PDF pendant plusieurs itérations.

### 5. Résilience par élément

Un fichier cassé ne doit jamais arrêter le run : `try/except` par robot,
on journalise et on continue. Créer des rapports d'erreurs dans le dossier logs/ sous format .md

---

## Architecture

```
src/
  common/          transverse cat1/cat2/cat3
    paths.py               racine + tous les chemins
    license_utils.py       allowlist licences
    llm_provider.py        anthropic|openai|gemini|template + garde-fou
    tokenizer_utils.py     comptage Qwen3 (+ repli approximatif)
    corpus_assembler.py    DocumentDraft + schéma JSONL
    contamination.py       recoupement avec le scénario d'évaluation
    contamination_scenarios.json   ^ sa configuration
    ocr.py                 repli PDF scanné (rastérisation + reconnaissance)
    run_report.py          rapports d'exécution .md dans logs/
  cat3/
    sources.py                   catalogue robots (SEUL endroit avec des noms en dur)
    pdf_manifest.json            catalogue manuels (config, vit avec le code)
    collect_pilot.py             ENTRÉE phase 1
    fetch_robot_descriptions.py  / fetch_git_source.py / xacro_render.py
    build_corpus.py              ENTRÉE phase 2
    download_manuals.py          ENTRÉE aide manuels
    urdf_parser.py               parsing déterministe
    urdf_adapter.py              voie URDF  → DocumentDraft
    pdf_adapter.py               voie PDF   → DocumentDraft

data/<cat>/
  raw/<kind>/<item_id>/        cat3 : kind = urdf | manuals
  raw/_cache/git/              clones, jamais dans le corpus
  metadata/collection_metadata.jsonl
  clean/corpus_clean.jsonl + corpus_stats.md

logs/
```

**Principe d'extension** : les deux voies produisent le même objet
intermédiaire `DocumentDraft`. Ajouter une source = ajouter un adaptateur,
sans toucher à l'assembleur ni au schéma de sortie. Ajouter une catégorie
= créer `src/cat1/` sur le même patron, `src/common/` reste inchangé.

### Imports

`src/` est la racine des paquets. Les points d'entrée font :

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> src/
```

puis `from common.x import y` / `from cat3.x import y`. Ne pas
réintroduire d'imports à plat (`from urdf_parser import ...`).

---

## Commandes

```bash
# vérifier la racine détectée (à faire en cas de doute sur les chemins)
python3 src/common/paths.py

# phase 1 — collecte (réseau + git requis)
python3 src/cat3/collect_pilot.py

# checklist des manuels PDF
python3 src/cat3/download_manuals.py --check

# phase 2 — corpus (hors ligne, descriptions gabarit)
python3 src/cat3/build_corpus.py --sources urdf

# phase 2 — run complet : manuels inclus, PDF scannés océrisés
python3 src/cat3/build_corpus.py --sources urdf,pdf --ocr

# phase 2 avec LLM
python3 src/cat3/build_corpus.py --sources urdf,pdf --ocr --provider gemini

# audit de contamination d'un corpus déjà écrit
python3 src/common/contamination.py --corpus data/cat3/clean/corpus_clean.jsonl
```

`--allow-proprietary-pdf` n'est plus nécessaire : la décision d'inclure les
manuels est figée entrée par entrée dans `pdf_manifest.json`
(`allow_no_license: true` + bloc `_decision`), donc reproductible sans
option de ligne de commande.

Variables d'environnement : `HERMES_ROOT`, `HERMES_LLM_PROVIDER`,
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`.

---

## Dépendances

```
robot_descriptions>=3.0.0
xacro>=2.1.1
pdfplumber>=0.11        # voie PDF (le repli pdftotext nettoie moins bien)
transformers>=4.51      # tokenizer Qwen3 exact (sinon comptage approximatif)
rapidocr-onnxruntime    # OPTIONNEL, seulement pour --ocr (pip pur, sans root)
```
Système : `poppler-utils` (`pdftotext`, `pdftoppm`, `pdfinfo`), `git`.

---

## Pièges connus

- **`robot_descriptions` 3.0.0 expose lui-même `XACRO_ARGS`.** 8 modules
  n'ont pas d'`URDF_PATH` (UR5e/UR10e, Kinova Gen3, xArm6/7, Franka
  FER/FR3) : il faut rendre le Xacro soi-même en passant ces args.
- **`$(find <pkg>)` où le paquet est la racine du dépôt** (ur_description,
  franka_description) : `xacro_render.py` préserve le nom du dépôt dans la
  copie temporaire, sinon la substitution casse. Ne pas renommer cette copie.
- **PDF : n'importe quel nom de fichier `.pdf` est accepté** dans
  `raw/manuals/<robot_id>/` (`pdf_adapter.find_pdf()` fait un glob).
  Ne pas réintroduire d'exigence de nom exact.
- **URDF Gazebo hérités** : préfixes XML non déclarés (`<sensor:camera>`)
  → ElementTree rejette tout le fichier (« unbound prefix »).
  `urdf_parser.read_urdf_xml()` déclare les préfixes manquants sur la
  racine avant parsing ; rien n'est supprimé, et la réparation remonte en
  avertissement.
- **Un `.pdf` qui n'en est pas un** : la signature `%PDF-` est vérifiée en
  premier, pour éviter l'opaque « No /Root object! » de pdfminer.
- **PDF scanné** : moins de 200 caractères extraits → erreur explicite
  invitant à relancer avec `--ocr`, pas d'enregistrement vide. L'OCR est
  mis en cache à côté du PDF (`.ocr-<nom>.json`) pour que régénérer le
  corpus ne relance pas la reconnaissance.
- **Pages « longues »** (manuel G1 : 1 page de 20 × 784 pouces, 627 Mpx à
  200 dpi) : `ocr.py` borne la largeur et découpe en bandes recouvrantes.
- **Texte OCR** : marqué `ocr: true` + `ocr_confidence` dans le corpus.
  L'OCR peut mal lire un chiffre — d'où le marquage, pour rester filtrable.
- **Tokenizer Qwen3** : nécessite un accès Hugging Face. Sans lui,
  `n_tokens_exact: false` dans chaque enregistrement.