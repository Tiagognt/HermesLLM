# RoboMix — DAPT corpus builder

This repository builds the **text corpus used for Domain-Adaptive
Pre-Training (DAPT)** of an open-weight Qwen3-family MoE model. The trained
model commands a **heterogeneous robot team** (wheeled rover, quadruped,
humanoid, manipulator arm, drone): it takes a natural-language mission such
as *"go save this man"* and produces task planning → task allocation →
per-robot planning → action-function selection.

It builds the **training data**, not the model.

**Current state: complete.** 1 202 documents, **2 421 834 Qwen3 tokens**,
contamination check passed, mandated category mix verified.

---

## 1. What is in this repository

### The deliverable

| File | What it is |
|---|---|
| **`data/full/corpus_full.jsonl`** | **The dataset.** One JSON object per line, 1 202 documents. |
| `data/full/corpus_full_stats.md` | Provenance record: mix, licenses, tiers, what was dropped and why. Keep it next to the trained model. |

Each line follows the schema required by the project brief, plus a few
auditability fields:

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

The mandated fields are `id, source, category, tier, license, url, lang,
text, n_tokens, collected_at`. The extras (`n_tokens_exact`, `source_type`,
`ocr`, `ocr_confidence`, and for cat1/cat2 `family`, `kind`, `rel_path`,
`repo_url`, `repo_commit`, `part`, `arxiv_id`) exist so the corpus can be
filtered and audited downstream without touching the required schema.

### The three categories

| Category | Tier | Content | Serves |
|---|---|---|---|
| **cat1** — General Robot Data | A | ROS 2 / Nav2 / MoveIt 2 / ros2_control docs, simulator docs, interface definitions, robotics algorithms, behaviour trees, planning-as-code | action functions, foundation for planning |
| **cat2** — HMRS Data | B | multi-robot decomposition, allocation and coordination: HMRS frameworks, the Open-RMF multi-robot book, 43 research papers | task planning, allocation, per-robot planning |
| **cat3** — URDF & Robot Specs | D | physical capabilities: DOF, mass, joint limits, payload, reach — URDF/Xacro plus vendor manuals | embodiment-aware allocation, feasibility |

Tier letters follow the project's master corpus taxonomy; the absence of a
tier C is expected, not an error.

### The files that matter

```
rebuild_dataset.sh              rebuild everything in one command

src/
  common/                       shared by the three categories
    paths.py                    project root + every path (single source of truth)
    license_utils.py            THE LICENSE ALLOWLIST
    contamination.py            evaluation-scenario overlap check
    contamination_scenarios.json  ^ its configuration
    dedup.py                    exact + near-duplicate removal (MinHash/LSH)
    secret_scrubber.py          API-key / credential redaction
    text_clean.py               rst/md cleaning + long-document splitting
    quota.py                    round-robin selection under a token cap
    tokenizer_utils.py          Qwen3 token counting
    corpus_assembler.py         DocumentDraft + the JSONL schema
    ocr.py                      scanned-PDF fallback
    git_repo.py                 shallow/sparse clone + license cross-check
    llm_provider.py             optional LLM + the numeric guardrail
    run_report.py               Markdown run reports
    merge_corpus.py             MERGE entry point

  cat1/sources.py               <- 28 source repositories, with their licenses
  cat2/sources.py               <- 6 repositories + 43 arXiv papers
  cat3/sources.py               <- 62 robots
  cat3/pdf_manifest.json        <- 12 vendor manuals + the recorded license decision

data/<cat>/
  raw/<kind>/<item_id>/         collected raw files
  raw/_cache/git/               git clones (gitignored, ~6.6 GB, regenerable)
  metadata/collection_metadata.jsonl   provenance, pinned commit, license per source
  clean/corpus_clean.jsonl + corpus_stats.md

logs/                           one Markdown report per run
```

The four `sources.py` / `pdf_manifest.json` files are the only places in
the codebase containing hard-coded source names. **Adding or removing a
source is an edit to those files alone.**

---

## 2. Rebuilding the dataset

### Install

```bash
pip install -r requirements.txt
sudo apt-get install -y git poppler-utils   # if missing
```

`xacro` here is the standalone PyPI package, not the ROS one — **no ROS
installation is required**. `rapidocr-onnxruntime` is optional and only
needed for `--ocr` on scanned manuals; it is a pure pip install (no root),
which is why it was chosen over Tesseract.

Environment variables: `HERMES_ROOT` (force the project root),
`HERMES_LLM_PROVIDER`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`GEMINI_API_KEY`.

### Everything at once

```bash
./rebuild_dataset.sh                # collect + build + merge
./rebuild_dataset.sh --build-only   # skip collection, rebuild from raw files
./rebuild_dataset.sh --collect-only # collection only
./rebuild_dataset.sh --refresh      # re-clone instead of using the cache
```

A full run from an empty cache takes roughly 20–40 minutes, dominated by
cloning ~34 repositories and by OCR of two scanned manuals. `--build-only`
takes about ten minutes and needs no network.

The script stops on the first failure, and `merge_corpus.py` **exits
non-zero if a mix band is violated** — so the whole thing is usable in CI
as-is.

### Step by step

```bash
# Sanity check: which project root is detected?
python3 src/common/paths.py

# --- PHASE 1: collection (network + git) ---------------------------------
python3 src/cat3/collect_pilot.py                 # 62 robots
python3 src/cat1/collect_docs.py                  # 28 repositories
python3 src/cat2/collect_hmrs.py                  # 6 repos + 43 papers

# useful variants
python3 src/cat1/collect_docs.py --only ros2_documentation,nav2_docs
python3 src/cat2/collect_hmrs.py --only papers
python3 src/cat3/download_manuals.py --check      # PDF manual checklist

# --- PHASE 2: corpus build (offline) -------------------------------------
python3 src/cat3/build_corpus.py --sources urdf,pdf --ocr
python3 src/cat1/build_corpus.py
python3 src/cat2/build_corpus.py

# resize a category without re-collecting anything
python3 src/cat1/build_corpus.py --budget-scale 0.75

# --- PHASE 3: merge ------------------------------------------------------
python3 src/common/merge_corpus.py
python3 src/common/merge_corpus.py --shuffle      # deterministic shuffle

# --- audits (any time) ---------------------------------------------------
python3 src/common/contamination.py               # every corpus
```

---

## 3. Method

### Two deliberately separate phases

- **Phase 1 — collection**: fetches raw files plus provenance and license
  metadata. Transforms nothing.
- **Phase 2 — transformation**: produces `corpus_clean.jsonl` and
  `corpus_stats.md`.

They have independent lifecycles. Regenerating the corpus — replaying the
token quotas, improving a cleaning filter, resizing a category — must never
require re-collecting. This is also why OCR results are cached next to
their source PDF and why arXiv papers are downloaded once.

Every path produces the same intermediate object, `DocumentDraft`, and
`corpus_assembler.py` is the only place that knows the output schema.
Adding a source = a catalogue entry; adding a *format* = an adapter.

### Phase-2 chain, in order

1. **Adaptation** — files become candidate documents. Granularity is chosen
   per nature: one file per document for docs and code, one *package* per
   document for ROS interface definitions (an isolated `.msg` is 30 tokens
   and meaningless out of context), one paper per document for arXiv.
2. **Secret scrubbing** — API keys, tokens, credentials in URLs. Values are
   replaced by an explicit marker so the teaching context survives.
   Documentation placeholders (`YOUR_API_KEY`, `<token>`) are spared.
3. **Contamination check** — see below.
4. **Deduplication** — exact (SHA-256) then near-duplicate (MinHash + LSH,
   Jaccard threshold 0.85).
5. **Token counting** — Qwen3 tokenizer (`Qwen/Qwen3-8B`). Every record in
   the current corpus has `n_tokens_exact: true`.
6. **Quotas** — a per-source cap, with round-robin selection over the
   source subtrees.
7. **Assembly** — JSONL record with its tier.

The order matters: deduplicating *before* the quotas guarantees the budget
is spent on unique content.

### Three decisions worth knowing

**Documentation is collected from its source repositories, not scraped.**
The brief suggested HTML scraping. All the target documentation (ROS 2,
Nav2, MoveIt, Gazebo, MuJoCo, PX4...) is generated from versioned `.rst`
and `.md` files. Taking the source removes the entire "strip nav/footer/
sidebar" problem, gives a verifiable LICENSE and a pinned commit, and makes
the collection reproducible.

**Quotas exist for diversity, not volume.** Available material far exceeds
the target: the ROS 2 documentation alone is ~1.18 M tokens. Without a cap
it would be half of cat1 and the model would learn the style of a single
source. Caps live in the `sources.py` files and are applied at build time,
so resizing never costs a re-collection.

**Deduplication is a measured necessity, not a refinement.** Gazebo
publishes its documentation in 12 parallel versions. On a `harmonic` vs
`ionic` sample, ~85% of same-named files are near-identical but only ~15%
are identical byte-for-byte — hash-based deduplication alone would miss
most of them. The catalogues therefore also pick a single version per
simulator upfront, leaving deduplication as a safety net.

### Contamination

The evaluation scenario — **a fire in a subway station** — must not appear
in the training corpus, otherwise the final evaluation is meaningless.
`common/contamination.py` enforces this across all categories,
deterministically and without an LLM, using two rule types declared in
`contamination_scenarios.json`:

- **phrase** — a scenario phrase appears verbatim;
- **cooccurrence** — at least one term from *each* group appears within the
  same N-character window. This is what separates "fire" in a safety manual
  (harmless) from "fire in a metro station" (contaminating).

Text is lowercased and de-accented before matching, so one configured term
catches `métro`/`metro` and survives OCR output. Every verdict carries the
rule that fired, the terms found and an excerpt — a rejection must be
justifiable. Adding an evaluation scenario means editing the JSON, never
the code.

The check runs inside each category, again at merge time, and can be run
standalone at any moment with `python3 src/common/contamination.py`.

### Where the source information lives

| You want to know | Look at |
|---|---|
| Which sources were used, and why | `src/cat1/sources.py`, `src/cat2/sources.py`, `src/cat3/sources.py` — each entry carries its license, its quota and a `notes` field explaining the choice |
| Which sources were **rejected**, and why | the header docstring of the same three files |
| Which vendor manuals, and under what decision | `src/cat3/pdf_manifest.json`, `_decision` block |
| The exact commit each source was taken from | `data/<cat>/metadata/collection_metadata.jsonl` |
| What happened during a given run | `logs/<timestamp>-<name>.md` — successes, traced exclusions, warnings, failures with full tracebacks |
| The final composition | `data/full/corpus_full_stats.md` |

Every source in `sources.py` had its license verified **by hand**, by
reading the repository's LICENSE file. That was not optional: the GitHub
API returned `NOASSERTION` for `navigation2`, `PythonRobotics`, `OMPL` and
`PX4-user_guide`, all four of which are in fact compliant. Collection
re-reads the file and reports any disagreement with the declared value.

---

## 4. License policy

### The allowlist

`src/common/license_utils.py` implements it, and it is the only place that
does:

```
MIT  ·  BSD-2-Clause  ·  BSD-3-Clause  ·  Apache-2.0  ·  CC-BY-x.x
```

Anything else is classified `flagged:<spdx>` and **never collected
automatically**. A source with no license at all becomes `no-license` and
is also excluded by default. Widening the allowlist is an explicit
decision, never a side effect.

### What that barrier actually rejected

| Source | License found | Outcome |
|---|---|---|
| TIAGo (`tiago_description`) | CC-BY-NC-ND-3.0 | rejected — kept in the catalogue so the exclusion stays traced |
| ProgPrompt (`NVlabs/progprompt-vh`) | NVIDIA License | rejected |
| slam_toolbox | LGPL-2.1 | rejected |
| bullet3 | zlib | rejected |
| Instruct2Act, SMART-LLM, CoELA, `ros_tutorials`, `ros-infrastructure/rep`, `gazebo_ros_pkgs` | no LICENSE file | rejected |
| **83 of 148 arXiv papers** | arXiv default (`nonexclusive-distrib`) | rejected — not redistributable |
| 17 further arXiv papers | CC-BY-NC-ND / NC-SA / SA-4.0 | rejected |
| 3 further arXiv papers | CC0-1.0 | rejected — see note below |

Two of the three "planning-as-code" sources named in the brief (ProgPrompt,
Instruct2Act) are therefore unusable; only Code-as-Policies survives. And
**more than half of the relevant multi-robot literature cannot be
redistributed at all** — arXiv's default licence is not an open licence.
That constraint is enforceable rather than assumed because arXiv publishes
each paper's licence through its OAI-PMH interface, which is what
`src/cat2/sources.py` records paper by paper.

CC0 is *more* permissive than CC-BY, so those 3 papers are arguably
includable — but `^CC-BY-\d\.\d$` does not match `CC0-1.0`, and widening
the allowlist is a decision to be taken deliberately. They stay out.

### The one deliberate exception

**13 documents carry `license: "no-license"`** — 85 278 tokens, 3.5% of the
corpus:

- **12 vendor manuals** (Unitree, Universal Robots, Kinova, Franka,
  ANYbotics, AgileX, Skydio, Bitcraze), downloaded **by hand** by the
  project owner. The brief explicitly authorises this route for cat3:
  *"Vendor manuals (Unitree / AgileX): do NOT scrape or redistribute —
  download the PDF, extract text locally, internal-training use only."*
- **1 URDF**, the AgileX Ranger Mini 3.0, whose repository carries no
  LICENSE file (verified through the GitHub API).

Three properties make this exception safe:

1. **It is recorded in a file, not in a command line.** `allow_no_license`
   is set entry by entry in `src/cat3/pdf_manifest.json`, next to a
   `_decision` block giving the date, the scope, the rationale and how to
   reverse it. The build is reproducible without passing any flag.
2. **It is scoped.** It widens neither the allowlist, nor the URDF path,
   nor any other category. Everything else in the corpus — 1 189 documents
   — is under a permissive license.
3. **It is filterable.** Those records keep `license: "no-license"` in the
   corpus. Dropping them is one line:
   `jq 'select(.license != "no-license")' corpus_full.jsonl`.

To reverse the decision: set `allow_no_license` back to `false` and re-run
phase 2. The manuals leave the corpus and are logged as set aside.

### Two related guarantees

**No hallucinated numbers.** Every figure in the cat3 corpus comes from
deterministic parsing (`urdf_parser.py`), never from an LLM. When an LLM
writes a capability description, `verify_numbers()` checks each number
against the extracted quantities and falls back to the deterministic
template on failure.

**OCR is marked.** Optical recognition can misread digits, so the two
OCR'd documents carry `ocr: true` and an `ocr_confidence` (0.977 and
0.981). Blocks below the confidence threshold are dropped, never guessed,
and recognised text is never "corrected" by heuristics.

---

## 5. Totals

| | Documents | Tokens | Share | Target band | Verdict |
|---|---:|---:|---:|---:|---|
| cat1 (tier A) | 966 | 1 648 225 | 68.1% | 60–70% | OK |
| cat2 (tier B) | 163 | 518 597 | 21.4% | 15–25% | OK |
| cat3 (tier D) | 73 | 255 012 | 10.5% | 10–15% | OK |
| **Total** | **1 202** | **2 421 834** | 100% | | **COMPLIANT** |

Counted with the Qwen3 tokenizer (`Qwen/Qwen3-8B`); every record has
`n_tokens_exact: true`. Median document 1 266 tokens, 95th percentile
6 277, maximum 12 219 — no single document dominates.

By license:

| License | Documents | Tokens |
|---|---:|---:|
| Apache-2.0 | 457 | 742 629 |
| CC-BY-4.0 | 360 | 847 837 |
| BSD-3-Clause | 195 | 376 290 |
| MIT | 157 | 314 295 |
| BSD-2-Clause | 20 | 55 505 |
| `no-license` (recorded exception) | 13 | 85 278 |

Quality gates on the final corpus: contamination **0 / 1 202**, exact and
near duplicates removed within each category and again across categories,
0 secrets found (the scrubber was verified separately against known key
patterns), 0 empty documents, all identifiers unique.

---

## 6. Known pitfalls

- **`robot_descriptions` exposes its own `XACRO_ARGS`.** Several modules
  have no `URDF_PATH` (UR5e/UR10e, Kinova Gen3, xArm6/7, Franka FER/FR3):
  the Xacro must be rendered locally, passing those args.
- **`$(find <pkg>)` where the package is the repository root**
  (ur_description, franka_description): `xacro_render.py` preserves the
  repository name in its temporary copy, otherwise substitution breaks.
- **Legacy Gazebo URDFs use undeclared XML namespace prefixes**
  (`<sensor:camera>`), which makes ElementTree reject the whole file.
  `urdf_parser.read_urdf_xml()` declares the missing prefixes before
  parsing; nothing is deleted, and the repair is reported as a warning.
- **PDF: any `.pdf` filename is accepted** in `raw/manuals/<robot_id>/`.
  Do not reintroduce an exact-name requirement.
- **A `.pdf` that is not a PDF**: magic bytes are checked first, so the
  error names the real content type instead of pdfminer's opaque
  *"No /Root object!"*.
- **Very long single-page PDFs**: the Unitree G1 manual is one page of
  20 × 784 inches (627 Mpx at 200 dpi). `ocr.py` caps the raster width and
  slices the page into overlapping bands.
- **`--only` replaces metadata rows, it does not append.** Appending made
  phase 2 adapt the same files twice, and the deduplicator then discarded
  the entire second pass.
- **Qwen3 tokenizer** needs Hugging Face access. Without it, records carry
  `n_tokens_exact: false` and the counts are approximate.

---

## 7. Open items

1. **Re-collect before training** so every `collected_at` is consistent,
   and archive `data/full/corpus_full_stats.md` alongside the trained
   model — it is the provenance record.
2. **Propagate `robot_class` and `fleet_priority`** from the cat3 metadata
   into its corpus records. The brief asks to *tag the fleet robots*; the
   `extra=` hook in `assemble_record()` makes this a small change.
3. **Decide on CC0** — 3 more research papers, under a licence more
   permissive than CC-BY but outside the allowlist pattern.
4. **An HTML adapter** would unlock Russ Tedrake's *Underactuated
   Robotics* (BSD-3-Clause), a full textbook currently out of reach
   because it is published as raw HTML rather than Markdown.
