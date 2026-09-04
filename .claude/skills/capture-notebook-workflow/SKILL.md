---
name: capture-notebook-workflow
description: Use when turning a Jupyter notebook into an OpenMS Streamlit app, when a notebook's analysis must become a tested standalone script, or when notebook code needs isolating from its plotting so it can run headless in a workflow.
---

# Capture a notebook workflow

Derive a testable processing step from a source notebook. Capture is not copying:
it classifies, isolates, and **proves the extraction reproduces the original**.

Vocabulary: `CONTEXT.md`. Rationale: `docs/notebook-to-webapp-design.md`.

## The rule

**Never write the extracted script before the source notebook has run.**

Without golden values a faithful extraction cannot be told from a plausible one,
and transcription errors in numeric code are invisible on inspection. If you
extracted first, throw it away and run the notebook.

## Sequence

1. **Find a Python.** Probe: active virtualenv → `python`/`python3`/`py` ≥3.10 →
   conda → `uv` → Docker. Report the one you chose, not the search. On Windows
   `python` on `PATH` is often a Microsoft Store stub that prints help and exits.
2. Classify every code cell statically, show the summary, and get confirmation
   before going further. **Not because execution is slow** — it usually is not.
   A teaching notebook runs in seconds precisely because it truncates. Nor
   because execution depends on the split: step 4 runs the notebook
   *unmodified*, so a wrong split wastes nothing there. The gate exists for the
   user. It is their first sight of their own notebook through this framework,
   every later stage inherits the reading, and a misread is cheapest to correct
   while it is still one table rather than a scaffolded app.
3. Pre-stage inputs, don't rewrite them. Copy data files beside a copy of the
   notebook; download cells guarded by `os.path.exists` become no-ops. Rewriting
   input cells invalidates the golden run.
4. **Execute once**, unmodified, `allow_errors=True`, and keep the executed copy.
   `nbclient` needs a kernelspec in the environment you chose.
   Report the runtime with its cause: `<runtime> — but only <n> of <total>
   spectra ran, because of the truncation` — never the number alone, which reads
   as "this analysis is cheap" when it means the opposite. Every number in that
   sentence comes from the run you just did. If you cannot say which line of the
   trace a figure came from, it does not go in.
5. Refine the classification against the execution trace, report only what
   changed, and confirm again if anything did. The trace sees which branch ran and
   which output is empty; static reading cannot. A cell producing no output is not
   automatically dead.
6. **Extract** the processing cells into `src/python-tools/<name>.py`.
7. **Generate the test** from the golden values and run it. It must pass. Say so
   as *"the extracted script reproduces your notebook"* — not *"extraction
   reproduces the notebook — 7/7 golden checks pass"*, which names this skill's
   stage and counts this skill's tests. The check total is how you know; that it
   reproduces their notebook is what they asked for.
8. Collect findings as one batch — do not interrupt to ask about them — and
   route each to the stage that owns it: shortcuts and suspicious constants to
   `interview-parameters`, hardcoded selections and display constants to the
   dashboard stage, exercise-cell sweeps to the interview as prior evidence.

If the user rejects part of the split, re-derive it. Re-read the cells named,
report what changed *and what did not*, and disagree with a line number as your
reason where you still disagree. Do not restate, and do not adopt a correction
without checking — a cell mixing scoring into plotting is genuinely ambiguous and
both of you can be half right. Then re-check whatever you classified by the same
reasoning.

## The summary

One table, shown before execution, and it is the whole turn. Rows are **steps of
the analysis, not cells** — a reader made to count cells to follow their own
notebook has been handed the framework's bookkeeping. Say what each step does and
where it lands in the app, in the same row; those are the two things the user
needs, and splitting them across a summary and a classification makes them do the
join.

```
<notebook>.ipynb — here is how I read it:

  loads the raw files and a sample sheet     ->  Upload page
  detects features in each run               ->  the analysis
  links them across runs                     ->  the analysis
  plots the intensity comparison             ->  Results page
  writes a per-protein summary               ->  Results page
  a parameter exercise at the end            ->  dropped, but I'll reuse
                                                 the numbers it printed

Look right? Then I'll run it once and come back with what needs deciding.
```

Contiguous cells doing one job are **one row**. Cell numbers appear only when the
user asks for them, or inside a finding that points at a specific line.

No number here may require having run the notebook — write "a feature table",
never a count of what is in it. And do not preview the findings: they arrive next turn with
their evidence and a recommendation attached, and naming them here spends the
budget twice to say the same thing worse.

## Cell classification

**This table is internal.** The `destination` column is written for you, not for the user: `code dropped, output harvested` is jargon. Classify with it, then say what the summary above
says: what the step does, and which page it becomes.

| class | destination | signals |
|---|---|---|
| `setup` | dropped | imports, version prints, `%matplotlib` |
| `input` | upload page | file loads, downloads, `os.path.exists` guards |
| `processing` | the python tool | transforms data into something an output is built from |
| `visualization` | dashboard stage | builds a figure, calls `.plot`/`.show` |
| `exercise` | code dropped, **output harvested** | teaching loops printing comparisons |
| `demo shortcut` | **review batch** | see findings below |

Not every notebook is a chain. An exploration notebook branches — a peak
count, a TIC, a spectrum — none downstream of another. Capture the shared prefix
once, emit each branch as its own output, and **say the outputs are parallel**:
that is what tells the dashboard stage the link identifier must be chosen rather
than inherited.

## Findings to collect (never fix silently)

| finding | how to detect | why it matters |
|---|---|---|
| truncation | `.head(n)` or a slice after a filter | ships an app that analyses a handful of whatever the user uploads |
| intent comment | "for this tutorial / demonstration" | code never meant to run in production |
| **discarded result** | an expression statement calling a non-mutating method (`sort_values`, `dropna`, `astype`) | the line does nothing; a bare `df.sort_values()` before `head(5)` silently changes *which* rows are analysed |
| suspicious constant | domain sanity check against units | a tolerance given as a *relative* `0.1` is 10%, where MS works in ppm |
| **hardcoded selection** | an index picking *which rows* to analyse — `exp[12]`, `df.iloc[0]`, a window used to **subset the data** before plotting | never a config parameter. The author picked one spectrum because a notebook shows one; an app shows whichever is clicked. It becomes a **link identifier** and a `filter_defaults` value. Followed literally, the app ships pinned to spectrum 12 forever |
| **display constant** | a literal encoding an assumption about the *magnitude* of the data — a marker-size divisor (`s=intensity/1e4`), a fixed colour-scale limit, a hand-set axis range or zoom window that changes only the **view**, not which rows are used, a log offset | tuned to one dataset's dynamic range and silently wrong on another: markers vanish or swamp the plot, a heatmap saturates. Not analysis, so it never reaches the tool; not a selection, so it is not a link identifier. Hand it to the dashboard stage to **derive from the data at render time**, or expose as a display control. Distinguish from a *layout* constant — `height=520`, `page_size=10` size the widget, not the data, and are correctly fixed |

Report each as a decision answerable in one word: **their line of code, where it
is, what it does to the app, and what you recommend.** Name what needs attention
rather than counting it — *"2 findings need review"* is a progress line wearing a
review's clothes. The cost is a parenthetical, never the lead —

```
Your notebook analyses only the first <n> of <total> spectra — `df.head(<n>)`,
cell <k>. Remove that for the app?   (recommended: yes, together with the
                            tolerance below — at the notebook's settings the
                            whole file takes <slow>, at <corrected> it takes
                            <fast>)
```

not *"the truncation costs <delta> to remove"*, which prices a decision the user
has not been shown and names nothing they wrote. Both sentences carry the
runtime, and it must stay: whether a truncation can be dropped still depends on
what it costs, and where corrected parameters turn seconds into minutes the user
has to hear that before agreeing. The difference is which of the two the sentence
is *about*.

The angle brackets are the point. Fill them from **this** run — never from an
example, and never from another notebook. Carrying a figure across notebooks is
how a report ends up confidently wrong.

Scan all six cell classes, not just the ones you are extracting. A hardcoded
selection lives in a `visualization` cell by nature, and that is a cell you are
about to drop — scan only `processing` and the class never fires. Where a finding
lands in a dropped cell, hand it to the stage that owns the cell: `visualization`
to the dashboard as a proposed `filter_defaults`, `exercise` to the interview as
prior evidence.

## Harvest an exercise cell before dropping it

Dropping the code is not discarding the result. A cell that sweeps a value and
prints a comparison is a sensitivity measurement the notebook already ran on real
data — the experiment `interview-parameters` is about to reproduce, for free.

Record which parameter it varied, over what range, and what moved. Keep it
distinct from golden values: a golden value says what the notebook produced, this
says how sensitive it was.

A flat sweep is a finding, not a null result. A teaching notebook will often ask
its reader to predict the effect of narrowing a tolerance while a default set a
few cells earlier already makes that sweep flat — so the exercise demonstrates
the opposite of what it means to teach. Tell the user that, in their own
numbers.

Never pass a flat sweep on as evidence of inertness. It is **masking until proven
otherwise**, and `interview-parameters` treats it that way. If a sweep cannot be
read this way, say so rather than guessing at it.

**A harvested sweep is never re-run.** Reading numbers the notebook already
printed costs nothing; reproducing them costs the longest wait in the framework,
to arrive at what is already on the screen. An exercise cell is there to teach —
it was written to be run once, by a student, as a demonstration. Take its result
as evidence about the parameter and drop the cell. Where its range is too narrow
to conclude from, say what it does not cover rather than sweeping it again.

## Isolation requirements

The emitted script imports no Streamlit and touches no `st.session_state` — online
mode runs it in an RQ worker that has neither. It takes a JSON parameter file as
`argv`, reads inputs from paths, writes outputs as files, exits nonzero on
failure, and declares `DEFAULTS` and `OUTPUTS` at module level.

`OUTPUTS` declares each file, its `role`, its `columns`, and the identifier it
links on. The dashboard stage reads it without executing anything, so it must be
accurate; the generated test asserts a real run matches it.

**`role` comes from a fixed vocabulary, because the dashboard stage looks it up
rather than interpreting it:**

```
table         a row per record, the thing a user scans and clicks
mirror        two spectra face to face
peakmap       retention time against m/z, as a density
chromatogram  a signal against retention time
```

An output that is none of these may coin a new role — but **say so in the
declaration**, because a coined role has no component waiting for it and the
dashboard will draw it with pyopenms-viz instead. Reaching for a new word when
one of these four fits is how a page loses the component it should have had: the
vocabulary was undocumented until a run mapped nothing at all and every role it
had was on this list.

Give every numeric entry in `DEFAULTS` an explicit `min` and `max`. Without them
the parameter probe invents bounds — `lo = 0` for a positive value — and sweeps a
value the tool rejects. The failed run is dropped from the effect calculation, so
the effect reads *lower* than the truth, which is the direction that produces
HARDCODE. A charge parameter swept to 0 is the case that found this.

## Golden values

Record per processing stage: row counts, column schemas, checksums over sorted
numeric columns. Record them **before** resolving any finding, so they describe
the notebook as written.

A printed golden value is formatted, not raw. `f"{x:.0f}"` *rounds*, so a
notebook printing `65094` may hold `65093.91`. Assert with `round()`, never
`int()` — truncating a correct extraction fails a test on working code, and the
obvious next move is to "fix" the extraction. Record the format spec beside the
value.

## Common mistakes

- **Serialising pyOpenMS objects.** Notebooks park `MSSpectrum` objects in
  DataFrame cells; none of it is serialisable. Converting to long-format parquet
  is genuine design — propose the shape, don't invent it silently.
- Extracting an exercise cell's code, or **discarding its output**. Two
  separate decisions, and the second is usually wrong.
- Silently dropping a truncation. It changes the golden values and the
  runtime. It is a finding, not a cleanup.
