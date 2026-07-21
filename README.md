# RoboMix — DAPT corpus builder

Tooling that assembles the **text corpus used for Domain-Adaptive
Pre-Training (DAPT)** of an open-weight Qwen3-family MoE model. The trained
model commands a **heterogeneous robot team** (wheeled rover, quadruped,
humanoid, manipulator arm, drone): it takes a natural-language mission such
as *"go save this man"* and produces task planning → task allocation →
per-robot planning → action-function selection.

This repository builds the **training data**, not the model.

---

## 1. Corpus design

The corpus is split into three categories, each serving a different stage
of the target model's reasoning.

| Category | Tier | Content | Serves | Status |
|---|---|---|---|---|
| **cat1** — General Robot Data | A | ROS 2 / Nav2 / MoveIt 2 / ros2_control docs, simulator docs, interface definitions, robotics algorithms, planning-as-code | action functions, foundation for planning | **complete** |
| **cat2** — HMRS Data | B | multi-robot decomposition / allocation / coordination — HMRS frameworks, the Open-RMF multi-robot book, and 43 CC-BY research papers | task planning, allocation, per-robot planning | **complete** |
| **cat3** — URDF & Robot Specs | D | physical capabilities: DOF, mass, joint limits, payload, reach — URDF/Xacro plus vendor manuals | embodiment-aware allocation, feasibility | **complete** |

Tier letters follow the project's master corpus taxonomy; the absence of a
tier C is expected, not an error.

### Token budget

The mandated mix is **cat1 60–70% · cat2 15–25% · cat3 10–15%**. All three
categories are built and the mix is **verified at merge time**:

| Category | Tokens | Share | Target band | Verdict |
|---|---:|---:|---:|---|
| cat1 | 1 648 225 | 68.1% | 60–70% | OK |
| cat2 | 518 597 | 21.4% | 15–25% | OK |
| cat3 | 255 051 | 10.5% | 10–15% | OK |
| **total** | **2 421 873** | 100% | | **CONFORME** |

`merge_corpus.py` exits non-zero if any band is violated, so the check is
usable in CI. The lever for rebalancing is `--budget-scale` on any
category's `build_corpus.py`: it re-emits a smaller or larger corpus in one
offline pass, with no re-collection.

Tokens are counted with the **Qwen3 tokenizer** (`Qwen/Qwen3-8B`). If
Hugging Face is unreachable the counter falls back to an approximation and
every record is marked `n_tokens_exact: false`.

### Output schema

One JSONL record per document, in `data/<cat>/clean/corpus_clean.jsonl`:

```json
{
  "id": "cat3-unitree_g1-urdf",
  "source": "robot_descriptions",
  "category": "cat3",
  "tier": "D",
  "license": "BSD-3-Clause",
  "url": "https://github.com/unitreerobotics/unitree_ros.git",
  "lang": "en",
  "text": "...",
  "n_tokens": 3412,
  "n_tokens_exact": true,
  "source_type": "urdf",
  "ocr": false,
  "collected_at": "2026-07-21T08:10:20+00:00"
}
```

`n_tokens_exact`, `source_type`, `ocr` and `ocr_confidence` are additions
beyond the required schema: they make the corpus auditable and filterable
downstream without altering the mandated fields.

---

## 2. Non-negotiable rules

These constraints shaped the architecture. Breaking one is a bug, not a
trade-off.

**1 — No hallucinated numbers.** Every figure in the corpus comes from
deterministic parsing (`urdf_parser.py`), never from an LLM. When an LLM
writes a description, `llm_provider.verify_numbers()` checks each number in
the generated text against the extracted quantities; on failure the
pipeline falls back to the deterministic template description.

**2 — License barrier.** Allowlist: MIT / BSD-x-Clause / Apache-2.0 /
CC-BY-x.x. Everything else becomes `flagged:*` and is never collected
automatically. `no-license` is collected only on an explicit, recorded
decision (`ALLOW_NO_LICENSE_FOR` in `collect_pilot.py`, or
`allow_no_license` in `pdf_manifest.json`).

**3 — Paths.** All paths go through `src/common/paths.py`. No relative
`../../data/` anywhere: scripts run from any working directory. The project
root is auto-detected and can be overridden with `HERMES_ROOT`. Paths
*stored* in JSONL are relative to the root so the project stays movable.

**4 — No silent skip.** Anything dropped — missing file, non-compliant
license, empty extraction, contamination — is logged with its reason and
counted in the final report. A silent `continue` is what once masked the
total failure of the PDF path for several iterations.

**5 — Per-item resilience.** One broken file never stops a run: `try/except`
per robot, log, continue. Every run writes a Markdown report to `logs/`.

---

## 3. Architecture

```
src/
  common/                        shared by cat1 / cat2 / cat3
    paths.py                     project root + every path
    license_utils.py             license allowlist
    llm_provider.py              anthropic|openai|gemini|template + number guardrail
    tokenizer_utils.py           Qwen3 token counting (+ approximate fallback)
    corpus_assembler.py          DocumentDraft + JSONL schema
    contamination.py             evaluation-scenario overlap check
    contamination_scenarios.json   ^ its configuration
    ocr.py                       scanned-PDF fallback (rasterize + recognize)
    run_report.py                Markdown run reports
    git_repo.py                  shallow/sparse clone + license cross-check
    dedup.py                     exact + near-duplicate (MinHash/LSH)
    secret_scrubber.py           API-key / credential redaction
    text_clean.py                rst/md cleaning + long-document splitting
    quota.py                     round-robin selection under a token cap
    merge_corpus.py              MERGE entry point (the three categories)
  cat1/
    sources.py                   source catalogue (ONLY place with hard-coded repos)
    collect_docs.py              PHASE 1 entry point
    build_corpus.py              PHASE 2 entry point
    text_adapters.py             rst/md/code/interfaces/notebooks → DocCandidate
  cat2/
    sources.py                   repo catalogue + 43 verified arXiv papers
    collect_hmrs.py              PHASE 1 entry point
    fetch_arxiv.py               arXiv full text (HTML, PDF fallback)
    build_corpus.py              PHASE 2 entry point
    text_adapters.py             docs/code/papers → DocCandidate
  cat3/
    sources.py                   robot catalogue (ONLY place with hard-coded names)
    pdf_manifest.json            manual catalogue + recorded license decision
    collect_pilot.py             PHASE 1 entry point
    fetch_robot_descriptions.py / fetch_git_source.py / xacro_render.py
    build_corpus.py              PHASE 2 entry point
    download_manuals.py          manual-download checklist
    urdf_parser.py               deterministic parsing
    urdf_adapter.py              URDF path → DocumentDraft
    pdf_adapter.py               PDF path  → DocumentDraft

data/<cat>/
  raw/<kind>/<item_id>/          cat1: docs|code|interfaces|notebooks
                                 cat2: docs|code|papers
                                 cat3: urdf|manuals
  raw/_cache/git/                clones, never part of the corpus (gitignored)
  metadata/collection_metadata.jsonl
  clean/corpus_clean.jsonl + corpus_stats.md

data/full/                       the merged deliverable
  corpus_full.jsonl + corpus_full_stats.md

logs/                            one Markdown report per run
```

### Two deliberately separate phases

- **Phase 1 — collection** (`collect_pilot.py`): fetches raw files plus
  provenance/license metadata. Transforms nothing.
- **Phase 2 — transformation** (`build_corpus.py`): produces
  `corpus_clean.jsonl` and `corpus_stats.md`.

They have independent lifecycles: descriptions must be regeneratable
**without re-collecting**. Never merge them. (This is also why OCR results
are cached next to their source PDF — re-running phase 2 must not re-run
recognition.)

### Extension principle

Every path produces the same intermediate `DocumentDraft`. Adding a source =
adding a catalogue entry; adding a *format* = adding an adapter, without
touching the assembler or the output schema. Adding a category = creating
`src/catN/` on the same pattern.

`src/common/` grew as the categories were built — `git_repo`, `dedup`,
`secret_scrubber`, `text_clean`, `quota` — but always by *promotion*: a
module moves into `common/` the moment a second category needs it, never
speculatively. Each promotion was checked byte-for-byte against the
previous corpus.

### Imports

`src/` is the package root. Entry points do:

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # -> src/
```

then `from common.x import y` / `from cat3.x import y`. Do not reintroduce
flat imports (`from urdf_parser import ...`).

---

## 4. Install

```bash
pip install -r requirements.txt
sudo apt-get install -y git poppler-utils   # if missing
```

`xacro` here is the standalone PyPI package, not the ROS one — **no ROS
installation is required**.

`rapidocr-onnxruntime` is optional and only needed for `--ocr`. It is a
pure pip install (no root, no system package), which is why it was chosen
over Tesseract.

Environment variables: `HERMES_ROOT`, `HERMES_LLM_PROVIDER`,
`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`.

---

## 5. Usage

```bash
# check the detected project root (when in doubt about paths)
python3 src/common/paths.py

# ---- cat1 ----------------------------------------------------------
# PHASE 1 — clone the 25 source repositories (needs network + git)
python3 src/cat1/collect_docs.py
python3 src/cat1/collect_docs.py --only ros2_documentation   # one source
python3 src/cat1/collect_docs.py --refresh                   # ignore the clone cache

# PHASE 2 — corpus (fully offline)
python3 src/cat1/build_corpus.py
python3 src/cat1/build_corpus.py --budget-scale 0.75         # smaller corpus
python3 src/cat1/build_corpus.py --dedup-threshold 0.9       # looser near-dup

# ---- cat2 ----------------------------------------------------------
# PHASE 1 — clone 6 repos + download 43 arXiv papers (~4 min, rate-limited)
python3 src/cat2/collect_hmrs.py
python3 src/cat2/collect_hmrs.py --only papers     # one of the two paths

# PHASE 2 — corpus (fully offline)
python3 src/cat2/build_corpus.py

# ---- cat3 ----------------------------------------------------------
# PHASE 1 — collection (needs network + git)
python3 src/cat3/collect_pilot.py

# PDF manual checklist (what is present, what passes the license barrier)
python3 src/cat3/download_manuals.py --check

# PHASE 2 — corpus, offline, deterministic template descriptions
python3 src/cat3/build_corpus.py --sources urdf

# PHASE 2 — full run: manuals included, scanned PDFs OCR'd
python3 src/cat3/build_corpus.py --sources urdf,pdf --ocr

# PHASE 2 — with an LLM writing the capability summaries
python3 src/cat3/build_corpus.py --sources urdf,pdf --ocr --provider gemini

# ---- merged deliverable ---------------------------------------------
# Merges the three categories, cross-deduplicates, re-checks contamination
# and VERIFIES the mandated mix. Exits non-zero if a band is violated.
python3 src/common/merge_corpus.py
python3 src/common/merge_corpus.py --shuffle       # deterministic shuffle

# standalone contamination audit of an already-written corpus
python3 src/common/contamination.py
```

The merge never modifies the per-category corpora: they remain the source
of truth, `data/full/` is a regenerable derivative.

Every run writes a report to `logs/<timestamp>-<name>.md` listing successes,
recorded exclusions, warnings and failures — with full tracebacks.

### Adding a robot

Edit **only** `src/cat3/sources.py` and add an entry to `PILOT_CATALOG`:

- if the robot exists in
  [`robot_descriptions.py`](https://github.com/robot-descriptions/robot_descriptions.py),
  use `SourceType.ROBOT_DESCRIPTIONS` + `description_module` (its license is
  read from the library, so it stays in sync with the source of truth);
- otherwise use `SourceType.GIT_REPO` + `repo_url` / `repo_ref` /
  `file_path_in_repo`, and fill `known_license_spdx` after reading the
  repository's actual LICENSE file (`None` if there is none).

No other file needs to change.

### Adding a PDF manual

Download it by hand — manufacturer sites are not to be scraped — and drop
it in `data/cat3/raw/manuals/<robot_id>/`. **Any `.pdf` filename is
accepted**; no renaming needed. Then add an entry to
`src/cat3/pdf_manifest.json`.

---

## 6. Quality gates

### License

The allowlist lives in `license_utils.py` and is never widened without an
explicit decision. Current cat3 breakdown:

| License | Records |
|---|---|
| BSD-3-Clause | 26 |
| Apache-2.0 | 12 |
| MIT | 9 |
| BSD-2-Clause | 3 |
| `no-license` | 13 |

The 13 `no-license` records are the manually downloaded vendor manuals plus
the AgileX Ranger Mini URDF. The consignes explicitly allow this route for
cat3 (*"download the PDF, extract text locally, internal-training use
only"*). The decision is **recorded in
`src/cat3/pdf_manifest.json` under `_decision`**, entry by entry via
`allow_no_license: true` — not passed as a command-line flag — so the run
is reproducible and the rationale travels with the repository. These
records keep `license: "no-license"` in the corpus and stay filterable.

`TIAGo` is a worked example of the barrier doing its job: published under
CC-BY-NC-ND-3.0, it is kept in the catalogue but excluded at collection
time and logged as such.

### Contamination

The evaluation scenario (**a fire in a subway station**) must not appear in
the training corpus. `common/contamination.py` enforces this for all
categories, deterministically and without an LLM, using two rule types
declared in `contamination_scenarios.json`:

- **phrase** — a scenario phrase appears verbatim;
- **cooccurrence** — at least one term from *each* group appears within the
  same N-character window. This is what separates "fire" in a safety manual
  (harmless) from "fire in a metro station" (contaminating).

Text is lowercased and de-accented before matching, so one configured term
catches `métro`/`metro` and survives OCR output. Every verdict carries the
rule that fired, the terms found and an excerpt — a rejection must be
justifiable.

Adding a new evaluation scenario means editing the JSON, never the code.

### OCR

Some vendor manuals are scanned images with no text layer. Native
extraction yields nothing, so `common/ocr.py` rasterizes with `pdftoppm`
and recognizes the text.

Long "scroll" pages are handled: the Unitree G1 manual is a single page of
20 × 784 inches (627 Mpx at 200 dpi). The module caps the raster width and
slices the page into overlapping horizontal bands, merging them while
dropping lines duplicated by the overlap.

**OCR output is not equivalent to native extraction.** Recognition can
misread digits, and rule 1 forbids doubtful numbers. Therefore:

- every OCR'd document carries `ocr: true` and `ocr_confidence` in the
  corpus, so it can be filtered or excluded downstream;
- blocks below the confidence threshold are dropped, never guessed;
- recognized text is never "corrected" by heuristics.

---

### Deduplication

`common/dedup.py` removes exact duplicates (SHA-256 of normalized text) and
near-duplicates (MinHash + LSH banding, Jaccard threshold 0.85, verified
after the LSH lookup so a bucket collision alone never rejects a document).

This is not a refinement, it is a measured necessity: Gazebo publishes its
documentation in **12 parallel versions**, ROS 2 one per distribution. On a
`harmonic` vs `ionic` sample, ~85% of same-named files are near-identical
but only ~15% are identical byte-for-byte — exact hashing alone would miss
most of them. The cat1 catalogue therefore also selects a *single* version
per simulator upfront, so deduplication is a safety net rather than the
primary defence.

Determinism matters here: the MinHash permutations come from a fixed-seed
PRNG and shingles are hashed with `crc32`, not Python's `hash()` (which is
randomized per process). Two runs produce byte-identical corpora.

### Secret scrubbing

`common/secret_scrubber.py` redacts AWS keys, GitHub/Slack/OpenAI tokens,
JWTs, private-key blocks, credentials embedded in URLs, and generic
`api_key = "..."` assignments. Values are replaced by an explicit marker
rather than deleted, so the teaching context survives while the value does
not. Documentation placeholders (`YOUR_API_KEY`, `<token>`, `$ENV_VAR`) are
deliberately spared — otherwise half the ROS tutorials would come out
censored. Every redaction is counted and reported.

## 7. Status

### cat1 — General Robot Data (tier A)

| | |
|---|---|
| Source repositories | 28 (all licenses hand-verified) |
| Corpus records | **966** |
| Tokens | **1 648 225** |
| Contamination check | **passed** — 0 overlap |
| Duplicates removed | 25 exact + 39 near |
| Secrets redacted | 0 found (scrubber verified separately on known patterns) |

Family mix: ros_docs · sim_docs · algorithms · examples · interfaces ·
planning_code. Licenses: Apache-2.0, CC-BY-4.0, BSD-3/2-Clause, MIT — **no
`no-license`, no `flagged:*`**.

Rejected after verification: ProgPrompt (NVIDIA License), slam_toolbox
(LGPL-2.1), Instruct2Act / ros_tutorials / REP / gazebo_ros_pkgs (no LICENSE
file). Two of the three planning-as-code sources named in the brief are
therefore unusable; only Code-as-Policies survives.

### cat2 — HMRS Data (tier B)

| | |
|---|---|
| Source repositories | 6 |
| Research papers | **43**, every one CC-BY-4.0 |
| Corpus records | **166** |
| Tokens | **518 597** |
| Contamination check | **passed** — 0 overlap |

Three complementary paths, because no single one suffices — the project's
dataset survey notes that RoCoBench is *"almost the only clean multi-robot
text source"*:

1. **HMRS frameworks** — EMOS/Habitat-MAS, RoCo/RoCoBench, PARTNR (all MIT).
   These hold the negotiation prompts and task definitions.
2. **The book** — *Programming Multiple Robots with ROS 2* (OSRF, CC-BY-4.0),
   the only complete text on the subject, plus Open-RMF: heterogeneous fleet
   management in production, where task allocation is a deployed system
   rather than an experiment.
3. **Research papers** — they carry the domain vocabulary (allocation,
   coalition formation, decomposition, embodiment-aware) that neither code
   nor documentation uses.

**arXiv publishes each paper's license through its OAI-PMH interface**, so
the barrier is enforceable rather than assumed. Of 148 relevant papers
queried:

| License | Count | Verdict |
|---|---:|---|
| arXiv default (`nonexclusive-distrib`) | 83 | **not redistributable** |
| CC-BY-4.0 | 45 | conforming — 43 kept, 2 off-topic |
| CC-BY-NC-ND-4.0 | 9 | outside allowlist |
| CC-BY-NC-SA-4.0 | 4 | outside allowlist |
| CC-BY-SA-4.0 | 4 | outside allowlist |
| CC0-1.0 | 3 | outside allowlist |

More than half of the relevant literature is simply not redistributable.
CC-BY-SA and CC0 are excluded because the allowlist is `^CC-BY-\d\.\d$` —
even though CC0 is *more* permissive than CC-BY, widening the allowlist is
an explicit decision, not something to slip in. Potential gain: 7 papers.

Rejected repositories: SMART-LLM and CoELA (no LICENSE file);
`habitat-lab` was dropped for a different reason — EMOS is a full fork of
it, so collecting both would have duplicated an entire simulator.

### cat3 — URDF & Robot Specs (tier D)

| | |
|---|---|
| Catalogue | 62 robots |
| Collected | 61 (1 excluded: TIAGo, CC-BY-NC-ND) |
| Corpus records | **73** — 61 URDF + 12 PDF manuals |
| Tokens | **255 051** (Qwen3, exact) |
| Contamination check | **passed** — 0 overlap on 63 documents |
| OCR'd records | 2 (mean confidence 0.977 and 0.981) |
| Outstanding | 1 — `unitree_h1`: the file on disk is an HTML page saved with a `.pdf` extension and must be re-downloaded |

Class distribution: arm 16 · humanoid 15 · quadruped 12 · mobile
manipulator 7 · biped 5 · wheeled 3 · drone 3 · dual-arm 1.

The ten robots added last were chosen for **morphological and vendor
diversity, not volume**: a hydraulic quadruped (HyQ), a direct-drive one
(Minitaur), a wheeled-legged biped (LimX), a heavy industrial arm (Fanuc),
a low-cost open-source arm (SO-ARM100), and three humanoid makers absent
from the catalogue. Forty-eight conforming modules were available; the
near-duplicate families were deliberately skipped — 8 Kinova Jaco2 variants
and 10 Universal Robots variants would have added tokens, not knowledge.

Priority fleet (Unitree G1, Unitree Go2, AgileX Ranger Mini) is present on
both the URDF and the manual path.

---

## 8. Known pitfalls

- **`robot_descriptions` exposes its own `XACRO_ARGS`.** Several modules
  have no `URDF_PATH` (UR5e/UR10e, Kinova Gen3, xArm6/7, Franka FER/FR3):
  the Xacro must be rendered locally, passing those args.
- **`$(find <pkg>)` where the package is the repository root**
  (ur_description, franka_description): `xacro_render.py` preserves the
  repository name in its temporary copy, otherwise substitution breaks. Do
  not rename that copy.
- **Legacy Gazebo URDFs use undeclared XML namespace prefixes**
  (`<sensor:camera>`), which makes ElementTree reject the whole file with
  *"unbound prefix"*. `urdf_parser.read_urdf_xml()` declares the missing
  prefixes on the root before parsing — nothing is deleted or rewritten,
  and the repair is reported as a warning, never silently.
- **PDF: any `.pdf` filename is accepted** in
  `raw/manuals/<robot_id>/` (`pdf_adapter.find_pdf()` globs). Do not
  reintroduce an exact-name requirement.
- **A `.pdf` that is not a PDF**: the magic bytes are checked first, so the
  error names the real content type instead of pdfminer's opaque
  *"No /Root object!"*.
- **Scanned PDF**: fewer than 200 extracted characters raises an explicit
  error suggesting `--ocr`, never an empty record.
- **Qwen3 tokenizer** requires Hugging Face access. Without it, records
  carry `n_tokens_exact: false`.

---

## 9. Status and next steps

**The dataset is complete.** All three categories are built, the mandated
mix is verified, and `data/full/corpus_full.jsonl` is the deliverable:
1 202 documents, 2 421 873 Qwen3 tokens, contamination check passed, zero
non-allowlisted license outside the 13 hand-downloaded vendor manuals whose
inclusion is recorded in `pdf_manifest.json`.

What remains open, in order of value:

1. **Re-download the Unitree H1 manual** — the file on disk is an HTML page
   saved with a `.pdf` extension. It is the only outstanding collection
   failure in the whole project.
2. **Propagate `robot_class` and `fleet_priority`** from the cat3 collection
   metadata into its corpus records. The brief asks to *tag the fleet
   robots*, and cat3 exists to serve embodiment-aware allocation. The
   `extra=` hook in `assemble_record()` — already used by cat1 and cat2 —
   makes this a small change.
3. **Decide on CC0 and CC-BY-SA.** Seven more research papers are available
   under licenses that are arguably compatible (CC0 is strictly more
   permissive than CC-BY), but the allowlist is `^CC-BY-\d\.\d$` and
   widening it is an explicit decision.
4. **An HTML adapter** would unlock Russ Tedrake's *Underactuated Robotics*
   (BSD-3-Clause), a full textbook currently out of reach because the book
   is published as raw HTML rather than Markdown.
5. **Re-run the whole chain before training** so every `collected_at` is
   consistent, and archive `data/full/corpus_full_stats.md` alongside the
   trained model — it is the provenance record.
