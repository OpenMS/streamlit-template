# Notebook → WebApp: framework design

How a Jupyter notebook becomes an OpenMS Streamlit application through natural
language. This is the design spec behind `.claude/skills/`; the user-facing
walkthrough is `docs/notebook_to_webapp.md`.

Vocabulary is fixed in [`CONTEXT.md`](../CONTEXT.md). Decisions that were close
calls are in [`docs/adr/`](./adr/).

---

## The arc

```
entry prompt (copied from the app's Quickstart page)
      │
      ▼
┌─────────────────────┐
│ opening             │  clone into a neutral folder, find a Python,
│                     │  ask which notebook, classify it STATICALLY,
│                     │  show the layered report, ask for a name
└─────────┬───────────┘
          │  app identity: folder, slug, class, pages
          ▼
source notebook
      │
      ▼
┌─────────────────────┐
│ capture             │  classify cells, isolate processing,
│                     │  execute source once for golden values
└─────────┬───────────┘
          │  src/python-tools/<name>.py   (DEFAULTS + OUTPUTS)
          │  tests/test_<name>.py         (golden values)
          ▼
┌─────────────────────┐
│ review interview    │  ONE batch pass, two sections:
│                     │  1. demo shortcuts + suspicious constants
│                     │  2. config parameters (sensitivity-probed)
└─────────┬───────────┘
          │  DEFAULTS finalized: shown / advanced / hardcoded
          ▼
┌─────────────────────┐
│ scaffold            │  WorkflowManager subclass, 4 content pages,
│                     │  app.py registration, settings.json identity
│                     │  DESIGN ROUNDS on Upload, then Configure
└─────────┬───────────┘
          │  app boots, config page renders, run works
          ▼
┌─────────────────────┐
│ dashboard           │  link graph → wireframe approval →
│                     │  DESIGN ROUND per panel, against the live app
└─────────┬───────────┘
          │  results page of linked Insight panels
          ▼
┌─────────────────────┐
│ usability gate      │  Playwright assertions + screenshot critique
└─────────┬───────────┘
          │  gate findings, phrased for a user
          ▼
    final DESIGN ROUND on the whole page, until "ship it"
```

Six skills: `notebook-to-webapp` orchestrates, and five stage skills each work
standalone against an existing application. *"Add an Insight dashboard to my
results page"* invokes `build-insight-dashboard` alone.

**The arc is a dependency graph, not a schedule.** It is drawn as a column because
that is the common path, but position is fixed by what a stage *consumes*: capture
must execute before extraction, and shortcuts must be resolved before parameters
are probed. The dashboard's link graph and wireframe read `OUTPUTS` alone — the
handoff `capture → dashboard` skips scaffold entirely — so they may be drawn while
the interview is still open. Only the panels need a running app. A reader given
the orchestrator skill found this parallelisation unprompted at tick 071 and was
marked wrong for it, because the rule said only "in order".

---

## The interaction model

The framework talks to a user in exactly two shapes, and they are not
interchangeable. Choosing the wrong one is the most common way to make this
framework unpleasant to use.

| | **interview** | **design round** |
|---|---|---|
| used when | something was measured | there is nothing to measure |
| shape | one batch, many rows | one thing, repeated |
| the user | adjudicates evidence | picks a direction |
| where | capture findings, config parameters | Upload, Configure, Results |

A design round is: **render it → show it → up to three suggestions, one per axis
→ a free field → an exit → apply → re-render**. The exit is always offered; the
user decides how many rounds something gets.

**Three is a ceiling, not a quota** (tick 007). Every suggestion must point at
something visible — except the first panel's behaviour suggestion, which by
definition names a panel that does not exist yet. Padding to reach three teaches
the user the list is decorative.
On a page the gate passes with no design notes the honest output is none, said
plainly — but only after the gate has run and the screenshot has been opened.

The three axes are **data** (what is shown or accepted), **layout** (how it is
arranged) and **behaviour** (what happens when the user acts, or before they
have). One suggestion per axis is what makes three suggestions three genuine
alternatives rather than three phrasings of one idea — and it is checkable, which
matters because guidance quality is otherwise only judgeable by taste.

Three principles cut across both shapes:

- **Show the thing before asking about it.** A question about something the user
  cannot see is a question they must imagine an answer to.
- **Every fork carries a recommendation.** The user came here to be guided.
- **Never ask for what you can determine.** The interpreter, the column types,
  the notebook's structure — find these. Ask only what is genuinely the user's:
  the name, what belongs on the config page, what the page should look like.

Why per-panel rather than whole-page rounds, and how the objection is repaired:
[`adr/0005`](./adr/0005-design-rounds-judge-one-panel.md).

---

## Shared preconditions

### Environment discovery

No stage may assume a particular Python. Probe in order and report the choice:

1. an already-active virtualenv (`VIRTUAL_ENV`)
2. `python` / `python3` / `py` on `PATH`, if ≥3.10
3. a conda environment (`CONDA_PREFIX`, or `conda env list`)
4. `uv` — create a scratch environment
5. Docker, using `Dockerfile_simple`

Report which was selected and why before doing anything that needs it.

#### Verified on the development machine (2026-08-31)

`python`/`python3` on `PATH` are Microsoft Store stubs, not interpreters, and
there is no conda — so discovery selects **step 4, `uv`**. Established working
baseline:

| | |
|---|---|
| interpreter | `uv` → CPython 3.12.13, venv at `streamlit-template/.venv` |
| analysis | `pyopenms 3.5.0`, `pyopenms-viz 1.0.0` |
| app | `streamlit 1.49.1`, `numpy 1.26.4` (pin held), `pandas 2.2.3`, `pyarrow 19.0.1` |
| dashboard | `openms-insight 0.2.0`, `polars 1.44.1` |
| gate | `playwright 1.62.0` + Chromium 151, launches headless at 1280×800 |
| TOPP tools | **150 binaries native on `PATH`** from `OpenMS-3.5.0-pre-FVdeploy-2026-01-29` — no Docker needed locally |
| fallback | Docker 29.4.3, Linux containers, 24 CPU / 33 GB |

**Test baseline: `pytest test_gui.py tests/` → 241 passed, 0 failed.**

An earlier version of this section excused two failures as pre-existing and
platform-specific. That excuse was withdrawn at tick 002: `test_seed_demos` passes
all 17 of its cases, and no test named `test_storage_health` exists in the
repository. The earlier failures were environmental, not properties of the suite.
**No failure is one a tick is entitled to ignore** — a standing allowance to
disregard named tests licenses dismissing a real regression that happens to land
on one of them.

### Non-interactive mode

Every stage supports `mode=auto`: take the recommended answer for every interview
row, never block. The self-improvement loop depends on this, and it is the only
sanctioned way to skip an interview.

---

## Stage 1 — `capture-notebook-workflow`

**In:** a source notebook. **Out:** a python tool, a golden-value test, a capture
report.

### Cell classification

Every code cell gets exactly one class:

| class | goes to | example from Task 2 |
|---|---|---|
| `setup` | dropped | `import pyopenms as oms`, version prints |
| `input` | upload page | `wget` of `.fasta` / `.mzML`, `MzMLFile().load` |
| `processing` | the python tool | digest, candidate search, TSG, alignment, scoring |
| `visualization` | dashboard stage | mirror plot cell |
| `exercise` | code dropped, **output harvested** | tolerance sweep loops, "predict first" prose |
| `demo shortcut` | **review interview** | `candidate_df.head(5)` |

Classification runs twice. The first pass is static -- AST, markdown headings,
comment text -- and is shown for confirmation before the notebook is executed,
because execution costs minutes and everything after is built on the split. The
second pass refines it against the golden run's execution trace, which sees which
branch ran and which output was empty; only what changed is reported, and a change
is confirmed again.

Both classification passes are shown for confirmation — the static one before the
notebook is executed, and the refined one only if the trace changed anything.
Capture is otherwise uninterrupted: every finding that needs a human is collected
for the single review pass in stage 2, never asked about mid-run.

### Isolation

The emitted script imports no Streamlit, takes a JSON parameter file as `argv`,
reads its inputs from paths, writes its outputs as files, and returns nonzero on
failure. Notebook-local helper functions come across as functions; module-level
statements become a `main()`.

### Golden values

The source notebook is executed once. Recorded per processing stage: row counts,
column schemas, and value checksums over sorted numeric columns. These become
fixtures. The extracted script must reproduce them exactly, or capture reports a
transcription defect and stops.

Golden values are recorded **before** demo shortcuts are resolved, so they
describe the notebook as written. Resolving a shortcut in stage 2 re-derives them.

### The output contract

```python
OUTPUTS = [
    {"key": "psms", "file": "psms.parquet", "role": "table",
     "id": "psm_id",
     "columns": ["psm_id", "spectrum_idx", "peptide", "score",
                 "n_candidates", "charge"]},
    {"key": "matched_peaks", "file": "matched_peaks.parquet",
     "role": "mirror", "links": {"psm": "psm_id"},
     "columns": ["psm_id", "side", "mz", "intensity", "ion_annotation"]},
    {"key": "fragments", "file": "fragments.parquet",
     "role": "sequence", "links": {"psm": "psm_id"},
     "columns": ["psm_id", "position", "residue", "b_matched", "y_matched"]},
]
```

`role` names what the data *is*, not which component draws it — the dashboard
stage owns that mapping. See [ADR 0002](./adr/0002-static-output-contract.md).

---

## Stage 2 — `interview-parameters`

One batch review, two sections, presented after capture completes.

### Section 1 — shortcuts and suspicious constants

Every demo shortcut and every constant that looks wrong, each with a proposed
resolution: **drop**, **promote to a config parameter**, or **keep as written**.

Detection rules:

- **truncations** — slices or `.head(n)` applied after a filter
- **intent comments** — "for this tutorial / demonstration / example"
- **discarded results** — an expression statement whose value is a call to a
  known non-mutating method, so the line does nothing. Task 2 has a bare
  `candidate_df.sort_values(...)` immediately before `head(5)`, which silently
  changes *which* five spectra are analysed
- **domain sanity** — a relative mass tolerance of 0.1 is 10%, where mass
  spectrometry works in ppm

Each shortcut is reported **with the runtime it costs**, measured from the golden
run and extrapolated to full scale. Whether to drop a truncation depends on what
the corrected parameters cost, so the number has to be on the screen when the
decision is made.

This section comes first because dropping a truncation changes the scale
everything else is measured at.

### Section 2 — config parameters

Candidates ranked by provenance:

1. named constants and default arguments (`missed_cleavages=2`)
2. `setValue` arguments (`tolerance`, `add_y_ions`)
3. inline literals
4. parameters of the underlying algorithm the notebook never touched

Tiers 1–2 are shortlisted and **probed**: re-run the processing step on a
downsampled input with each numeric parameter perturbed, and report the measured
effect on the outputs.

**A parameter that probes as inert is never recommended `hardcode` on that
evidence alone.** It must first be re-probed with each other numeric parameter
driven to its neutral value. If its effect appears under some setting of another,
the finding is *masking*: report the interaction and keep both.

This rule exists because the naive version fails on the hero example. Task 2's
`absolute_tolerance` moves candidate counts by 0.7% as shipped — because
`relative_tolerance=0.1` opens a ±169 Da window that swamps it — yet it is the
most important parameter in the notebook. Inert-in-isolation and genuinely-inert
are different findings and must not share a recommendation. Evidence:
[`eval/baseline-task2.md`](../eval/baseline-task2.md).

Each row resolves to one of: **shown**, **advanced** (`"advanced": True`),
**hardcoded** (absent from `DEFAULTS`), or **dashboard control** (a display-time
choice, handed to stage 4).

A widget type is proposed with each kept parameter. Anything intended to be
driven by a preset gets an **explicit** `widget_type` — auto-typed numeric,
selectbox and multiselect widgets double-prefix their session key, and presets
silently fail to apply to them.

---

## Stage 3 — `scaffold-workflow-app`

Generates the `WorkflowManager` subclass, four content pages, `app.py`
registration, and application identity in `settings.json`.

Non-negotiables, each a known way to produce a silently broken app:

- `execution()` is annotated `-> bool` and returns `True` only when every step
  succeeded; every `run_python()` call is gated on its return value.
- `page_setup()` runs before the workflow object is constructed.
- `configure()` and `results()` are decorated `@st.fragment`.
- Anything reachable from `execution()` is free of `st.session_state` — in online
  mode it runs inside an RQ worker that has none.
- `get_files()` raises on an empty list; the user's selection is guarded first.
- The workflow slug is chosen once and never changed.

Sits beside `create-workflow` and `create-page`, which remain loadable
skills for their own routes; this stage is the path for a *captured* python tool.

---

## Stage 4 — `build-insight-dashboard`

### Step 1 — link graph

Derived from the output contract. Each output's `role` maps to a component; each
`links` entry becomes a link identifier. Components with no matching output are
skipped explicitly rather than silently.

```
psms.parquet          → Table         sets    'psm'
matched_peaks.parquet → MirrorPlot    filters 'psm'
fragments.parquet     → SequenceView  filters 'psm'
```

When no Insight component fits a role, fall back to pyopenms-viz through
`show_fig()` and say so in the wireframe — a fallback is a design decision the
user should see, not a silent substitution.

### Step 2 — wireframe

Approved **before any code is written**. Shows placement, sizes, what each panel
sets and what it filters on.

### Step 3 — panels, one design round each

One panel at a time against the running app. Chrome is driven directly here so
the model sees the page as it is designed, and each panel gets a design round —
screenshot, up to three suggestions on data / layout / behaviour, a free field, an exit
— before the next panel is built.

The first panel has nothing to link to, so its behaviour suggestion is necessarily
a promise about a panel that does not exist yet. It must name that panel, or it
reads as arbitrary.

Streamlit does not re-import an already-imported `src/` module, so applying a
suggestion requires a server restart. Skipping it shows the user the panel they
just changed, unchanged, and they conclude the framework ignored them.

### Step 4 — the final round, on the whole page

Per-panel rounds cannot see what only exists once everything is on screen: the
summary strip, column ratios between panels, one colour meaning one thing
throughout, and what the page looks like before anything is selected — the state
every user sees first and the one built last.

So the gate runs *before* the last round, and its findings become that round's
suggestions. Repeats until the user ships it. See
[`adr/0005`](./adr/0005-design-rounds-judge-one-panel.md).

### Style contract

Applied here, enforced in stage 5:

**Layout** — a summary strip of 3–5 headline numbers first; no panel taller than
the viewport; column ratios follow panel role, never a default even split.

**Semantics** — one colour per concept, identical in every panel (b-ions blue,
y-ions red, unmatched grey); axis labels carry units and never expose a raw
column name (`mz` → `m/z`, `rt` → `Retention time (s)`).

**States** — nothing-selected shows an instruction, not a blank; no-results-yet
points at the Run page; a traceback never reaches the UI.

**Theme** — primary, secondary and font set in `.streamlit/config.toml`.

---

## Stage 5 — `verify-webapp-usability`

Headless Playwright at 1280×800. Hard assertions:

- page boots with no Python traceback
- browser console has zero errors
- every declared panel renders with real width and height (*vertical* placement
  is not asserted: below-the-fold is a design note, not a failure)
- each component iframe is non-empty and reports the expected row count
- **no panel is stuck loading** — a panel filtering on a link identifier nothing
  sets and no `filter_defaults` covers shows "Loading…" forever while passing
  every other assertion: real iframe size, clean console, nothing thrown. The
  gate reads inside each iframe after settling and fails on a panel whose entire
  content is a placeholder
- clicking a row in the master panel changes the linked panels' payloads
- no horizontal scrollbar
- first paint within budget

Then a screenshot the model critiques against the style contract. Assertions
catch breakage; the critique catches ugliness. Both are recorded.

**The gate has a second job.** Run before the dashboard's final design round, it
also emits *design notes* — panels below the fold, a missing summary strip, a
column header with no slack left. These are observations rather than failures, and they are
written to be read by a user, not by a log.

Kept as a permanent gate in `tests/`. AppTest is retained for what it can still
see — see [ADR 0003](./adr/0003-browser-verification-for-insight-pages.md).

---

## The tutorial

`docs/notebook_to_webapp.md`, single-sourced into the in-app documentation page.
Registering it means editing the `pages` list in `content/documentation.py` **and**
the `test_documentation` parametrize list in `test_gui.py`, or CI breaks.

Hands-on, full scope, built on `EUBIC_Task2_ID.ipynb`. Roughly two screens of
prose: a prerequisites check, then the stages, each with a "you should now see
this" checkpoint and a tag to jump to if the reader's machine fails them.

It starts at the **Quickstart page**, not at a slash command — the entry prompt is
the real front door, and a tutorial that starts anywhere else documents a path
nobody takes.

**One round per kind, not one per page.** Rounds are the framework's longest
interaction by a wide margin, and the tutorial's budget is thirty minutes. It
walks three in full — a page round on Configure, a panel round on the first
panel, and the whole-page round the gate feeds — because each differs from the
others in a way a reader has to see. It then states that Upload and the remaining
panels work identically rather than showing them. The cap belongs on the
tutorial, not on the framework.

### Why Task 2 is the hero example

It maps onto OpenMS-Insight almost exactly — the notebook's payoff is a mirror
plot of observed against theoretical spectra with b/y ion annotations, and
Insight ships `MirrorPlot` and `SequenceView` for precisely that. The parameter
surface is rich (`missed_cleavages`, peptide length bounds, enzyme, precursor
tolerance, ion-type toggles, alignment tolerance). Cell 22 is *already* a
sensitivity sweep over the precursor tolerance, so the probe has ground truth
handed to it. And it carries two real traps — a `head(5)` demo truncation and a
`relative_tolerance=0.1` that means 10% — which make the review interview
demonstrably worth doing.

Output lands in a sibling directory (`../eubic-id-app`), cloned from the template,
so the template checkout stays clean and the result is a real standalone app.

---

## The self-improvement loop

Driven by `/loop` with no interval — ticks cost real compute and pace themselves.

### Each tick

1. Run the corpus headless and score artifacts. A drop stops the tick.
2. Run the framework end to end under a persona (below), saving the transcript.
3. Pick the single worst moment in that transcript.
4. Make **one** skill edit.
5. Re-run the same persona, saving the new transcript.
6. Judge the two transcripts blind. One persona is judged per tick by default, so
   its verdict is the tick's verdict; a tie counts against the edit. Where a tick
   judges several personas — worth doing for a change that touches every
   stage — a majority is required, and a split is a revert.
7. All corpus notebooks above threshold → add a notebook by a different author.

Stop after three consecutive ticks with no commit, and report the plateau rather
than churning.

### Two measurements, measured differently

**Artifacts** — capture split accepted, golden values reproduced, tests pass, app
boots, panels built vs. planned, usability gate result, minus human fixes. Scored
numerically by `eval/run_eval.py`. These are **saturated at 1.00** across the
current corpus and no longer discriminate between skill edits; they are retained
as the regression guard, which has already caught one broken harness.

**Guidance** — how well the skill guided its user. Has no absolute scale. Judged
by `eval/judge.py`, which shuffles the before-edit and after-edit transcripts into
X and Y, hides the mapping, and asks a judge which guided better and why. The
reason is as valuable as the verdict: it names the next tick's edit, which a
number never does.

An absolute rubric was rejected because it varies by roughly ±0.4 on a 5-point
scale between reruns of an *unchanged* skill — larger than a typical skill edit's
effect, so a ratchet built on it keeps edits that changed nothing, invisibly. See
[`adr/0004`](./adr/0004-guidance-is-judged-pairwise.md).

The judge must not be the context that made the edit. Blindness is enforced
mechanically as far as it can be — separate key file, revealed only on `record` —
but nothing stops a judge opening it, so this is finally a discipline.

### Personas

Auto-accept alone would only ever measure code generation — the interviews and
design rounds, which are the product, would go unmeasured. So ticks rotate a
persona:

| persona | behaviour | measures |
|---|---|---|
| `auto` | takes every recommendation and first suggestion | baseline generation quality |
| `sceptic` | rejects the first split, demands a redo | does it re-derive or repeat itself? |
| `novice` | asks what a term means | does it explain, or restate the question? |
| `expert` | wants the full algorithm surface exposed | does it degrade gracefully? |
| `minimal` | wants two parameters, everything else hidden | does it respect a hard constraint? |
| `designer` | rejects all three suggestions, always uses the free field | are the axes real, or only its own ideas handled? |

`designer` exists because the design round is the newest mechanism in the
framework and the free field is the part most likely to be handled badly.

### Corpus

Starts at EuBIC Task 1, Task 2, Task 3. Grows when all members clear threshold —
the guard against tuning the skills into three notebooks by one author.

### Artifacts

`eval/scores.jsonl` holds one row per tick; `eval/tick-NNN/` holds that tick's
screenshots, transcripts and diff.

---

## Assumptions

- One source notebook produces one captured workflow. Running the orchestrator
  again adds a second workflow to the same app.
- OpenMS-Insight becomes a dependency of generated apps. It is not, and does not
  become, a dependency of the template itself.
- The eight existing flat `.claude/skills/*.md` playbooks are converted to real
  loadable skills as part of this work — with no frontmatter and no directory,
  nothing currently surfaces them.
