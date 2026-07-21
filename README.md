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
| **cat2** — HMRS Data | B | multi-robot decomposition / allocation / coordination text (RoCoBench, EMOS / Habitat-MAS, SMART-LLM, PARTNR) | task planning, allocation, per-robot planning | not started |
| **cat3** — URDF & Robot Specs | D | physical capabilities: DOF, mass, joint limits, payload, reach — URDF/Xacro plus vendor manuals | embodiment-aware allocation, feasibility | **complete** |

Tier letters follow the project's master corpus taxonomy; the absence of a
tier C is expected, not an error.

### Token budget

The mandated mix is **cat1 60–70% · cat2 15–25% · cat3 10–15%**. With cat1
and cat3 built, the remaining freedom is fully determined:

| | Share | Tokens |
|---|---|---|
| cat1 (built) | 60–70% | **1 507 283** |
| cat3 (built) | 10–15% | **236 604** |
| **cat2 (to build)** | 15–25% | **410 000 – 581 000** |
| Whole corpus | 100% | 2.15 M – 2.32 M |

That cat2 window is the binding constraint for the next step: it is the
only interval satisfying all three ratio bands at once. The dataset survey
warns that clean multi-robot text is scarce, so **if cat2 falls short,
shrink cat1 rather than pad cat2** — `cat1/build_corpus.py --budget-scale
0.75` re-emits a smaller, still-balanced cat1 in one offline pass, with no
re-collection.

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
  cat1/
    sources.py                   source catalogue (ONLY place with hard-coded repos)
    collect_docs.py              PHASE 1 entry point
    build_corpus.py              PHASE 2 entry point
    text_adapters.py             rst/md/code/interfaces/notebooks → DocCandidate
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
  raw/<kind>/<item_id>/          cat3: kind = urdf | manuals
  raw/_cache/git/                clones, never part of the corpus
  metadata/collection_metadata.jsonl
  clean/corpus_clean.jsonl + corpus_stats.md

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

Both paths produce the same intermediate `DocumentDraft`. Adding a source =
adding an adapter, without touching the assembler or the output schema.
Adding a category = creating `src/cat1/` on the same pattern;
`src/common/` stays unchanged.

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

# standalone contamination audit of an already-written corpus
python3 src/common/contamination.py --corpus data/cat3/clean/corpus_clean.jsonl
```

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
| Source repositories | 25 (all licenses hand-verified) |
| Corpus records | **876** |
| Tokens | **1 507 283** (Qwen3, exact) |
| Median / max document | 1 077 / 9 434 tokens |
| Contamination check | **passed** — 0 overlap |
| Duplicates removed | 23 exact + 34 near |
| Secrets redacted | 0 found (scrubber verified separately on known patterns) |

Family mix: ros_docs 43% · sim_docs 24% · algorithms 14% · examples 11% ·
planning_code 5% · interfaces 3%.

Licenses: Apache-2.0 419 · CC-BY-4.0 226 · BSD-3-Clause 144 · MIT 67 ·
BSD-2-Clause 16. **No `no-license` and no `flagged:*` record.**

Sources rejected after verification: ProgPrompt (NVIDIA License),
slam_toolbox (LGPL-2.1), Instruct2Act / ros_tutorials / REP / gazebo_ros_pkgs
(no LICENSE file). Two of the three planning-as-code sources named in the
brief are therefore unusable; only Code-as-Policies survives.

### cat3 — URDF & Robot Specs (tier D)

| | |
|---|---|
| Catalogue | 52 robots |
| Collected | 51 (1 excluded: TIAGo, CC-BY-NC-ND) |
| Corpus records | **63** — 51 URDF + 12 PDF manuals |
| Tokens | **236 604** (Qwen3, exact) |
| Contamination check | **passed** — 0 overlap on 63 documents |
| OCR'd records | 2 (mean confidence 0.977 and 0.981) |
| Outstanding | 1 — `unitree_h1`: the file on disk is an HTML page saved with a `.pdf` extension and must be re-downloaded |

Class distribution: humanoid 12 · arm 12 · quadruped 10 · mobile
manipulator 7 · biped 5 · drone 3 · wheeled 2 · dual-arm 1.

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

## 9. Next steps

1. **Build cat2** (HMRS, tier B) against the **410 k – 581 k token** window
   in section 1, reusing `src/common/` unchanged. This is the scarce
   category: RoCoBench, EMOS / Habitat-MAS, SMART-LLM and PARTNR are the
   named candidates, and their licenses must be verified one by one before
   anything is collected.
2. Re-download the Unitree H1 manual (the current file is HTML).
3. Propagate `robot_class` and `fleet_priority` from the cat3 collection
   metadata into its corpus records — the brief asks to *tag the fleet
   robots*, and cat3 exists to serve embodiment-aware allocation. The
   `extra=` hook in `assemble_record()` (already used by cat1) makes this a
   small change.
4. Run the cross-category deduplication pass once cat2 exists: `dedup.py`
   currently runs within a category, and cat1/cat2 may overlap on
   planning-as-code material.
5. Decide the final mix and emit it: with all three categories built,
   `--budget-scale` on cat1 is the lever that makes the three ratio bands
   hold simultaneously.
