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
| **cat1** — General Robot Data | A | ROS2 / ROS1 / MoveIt2 / Nav2 docs, license-cleared robotics code, planning-as-code | action functions, foundation for planning | not started |
| **cat2** — HMRS Data | B | multi-robot decomposition / allocation / coordination text (RoCoBench, EMOS / Habitat-MAS, SMART-LLM, PARTNR) | task planning, allocation, per-robot planning | not started |
| **cat3** — URDF & Robot Specs | D | physical capabilities: DOF, mass, joint limits, payload, reach — URDF/Xacro plus vendor manuals | embodiment-aware allocation, feasibility | **complete** |

Tier letters follow the project's master corpus taxonomy; the absence of a
tier C is expected, not an error.

### Token budget

The mandated mix is **cat1 60–70% · cat2 15–25% · cat3 10–15%**. cat3 is
finished and therefore fixes the scale of everything else:

| | Share | Tokens |
|---|---|---|
| cat3 (built) | 10–15% | **236 604** |
| **Whole corpus (implied)** | 100% | **1.58 M – 2.37 M** |
| cat1 (to build) | 60–70% | ~0.95 M – 1.66 M |
| cat2 (to build) | 15–25% | ~0.24 M – 0.59 M |

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

## 7. cat3 status

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

1. Re-download the Unitree H1 manual (the current file is HTML).
2. Propagate `robot_class` and `fleet_priority` from the collection
   metadata into the corpus records — the consignes ask to *tag the fleet
   robots*, and cat3 exists to serve embodiment-aware allocation.
3. Add near-duplicate detection in `src/common/` before cat1/cat2 scale up
   (template-generated descriptions of 12 humanoids are structurally very
   similar).
4. Build cat1 and cat2 against the token budget in section 1, reusing
   `src/common/` unchanged.
