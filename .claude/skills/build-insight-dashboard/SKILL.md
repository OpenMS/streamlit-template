---
name: build-insight-dashboard
description: Use when building or changing an OpenMS Streamlit results page with OpenMS-Insight components, when panels must be linked so clicking one filters another, or when a results page needs a table, mirror plot, heatmap or volcano plot.
---

# Build an Insight dashboard

Turn a processing step's declared `OUTPUTS` into a results page of linked panels.
Works standalone against an app that already has results.

## The rule

**Build one panel at a time, look at it, and design it with the user before
building the next.**

## 1. Link graph

Read `OUTPUTS`. Map each `role` to a component and each `links` entry to a link
identifier. State skipped components explicitly — a component with no matching
output is a decision, not an omission.

```
psms.parquet          role=table   -> Table         sets    'psm'
mirror_peaks.parquet  role=mirror  -> MirrorPlot    filters 'psm'
                                   -> VolcanoPlot   SKIPPED, no groups
```

Where no Insight component fits, fall back to pyopenms-viz via `show_fig()` **and
say so in the wireframe**.

Where outputs are **parallel** rather than chained, no panel inherits the link
identifier. Choose one and say why — usually the table, being what a user looks at
first.

## 2. Wireframe

Approve placement, sizes, and what each panel sets and filters on, **before
writing code**.

## 3. Panels, one at a time — each with a design round

One round:

1. Render it, and have it **on screen in the user's browser**. Screenshot it for
   yourself — that is how you see the truncated header and the flattened axis —
   and never mention having done so. Taking a screenshot is not news; the panel
   is.
2. **Resolve every candidate to its edit before offering it.** In thinking, name
   the file and the change that implements it. A candidate whose edit you cannot
   name is dropped; one whose edit turns out bigger or smaller than the wording
   implied is reworded to match before anyone sees it. This is the only defence
   against walking a suggestion back after it has been accepted — and the cost of
   that is not one suggestion, it is the user's trust in every one that follows.
3. Ask them **one at a time**, best first — a question, not a list. At most
   three per round, one per axis: three is a ceiling, not a quota, and it is
   never a ceiling on a single screen. Three at once is a pile rather than a
   choice, and a user holding three open decisions makes none of them.
4. Offer a free field and an exit, both always, at every step.
5. Apply, restart the server, tell them to refresh, offer another round. Without
   the restart you show the user their unchanged panel — Streamlit does not
   re-import an edited `src/` module.

| axis | means | example |
|---|---|---|
| **data** | what the panel shows | "each row carries retention-time bounds; they explain what the 3D view draws" |
| **layout** | how it is arranged | "this header truncates at the width you gave it" |
| **behaviour** | interaction, or the state before any | "a row click selects the feature the 3D panel draws" |

Three is a ceiling, not a quota. Every suggestion must point at something the
user can see — except the first panel's behaviour suggestion, which by definition
points at a panel that does not exist yet and must name it. If only two axes have
anything real to say, offer two and name the third as clean. Offering none is
legitimate — but only after you have rendered the panel and opened its
screenshot; in the final round, only after the gate has run as well.

The first panel has nothing to link to yet, so name the panel its behaviour
suggestion is preparing for, or it reads as arbitrary.

## Answering the free field

Where a user with a design opinion spends every round. **Check the request against
the component and the data before attempting it**, then answer in one of five
shapes — the failure is conflating them:

| shape | when |
|---|---|
| **yes** | component and data both support it |
| **yes, and here is what you lose** | possible, but it costs a property the panel has — name the cost first |
| **not as stated** | a hard constraint forbids it — give the number, offer what fits |
| **yes, but it reopens an earlier stage** | the data does not exist; say which stage and what re-running costs |
| **no** | the component cannot express it; offer the nearest thing it can |

Real examples: *colour peaks by ion type* → **no** (`highlight_column` is binary
and already carries `matched`); *add a protein column* → **reopens capture** (the
tool never computed one); *table beside the mirror plot* → **not as stated**
(these headers measure ~645px at this font; half-width is ~320px); *two spectra at once* → **yes,
losing** observed-vs-theoretical.

**Never silently substitute.** A refusal with a reason beats a substitution every
time.

## 4. The final round, on the whole page

Run the usability gate **first**, then open a round using what it and the
screenshot found.

**Never name the gate, and never give its score.** Not as a finding, not as
reassurance, not as `11/11`. It is a check this framework runs on itself; the
user is looking at their own results page and has no idea a gate exists. The same
goes for the screenshot — saying you took one is narrating machinery.

| state | what they read |
|---|---|
| checks pass · picture shows 2 problems | two things I'd change |
| checks pass · picture clean | *(neither is mentioned — describe the page)* |
| truncated header found | that column title is cut off |

The left column is shorthand for your own state, never a sentence to adapt. A
run that read *"The gate is clean but the picture shows three things worth
fixing"* had reassembled row one into prose — the shape survives being told not
to name the gate, because the contrast is what carries it. **There is no
user-facing sentence in which the two halves appear together.**

Measured in **4 builds of 8**, always in the same shape: a pass count, then a
contrast between what the checks caught and what the picture showed. The rule
above this used to govern *findings* only, so a status report about the check
itself walked straight through it — and the paragraph below used to say *"say
exactly that"* about a green gate, which reads as permission to name it.

Phrase what the gate found for a user, not a log: *"nothing is selected when the
page opens, so the 3D panel is empty on arrival"*.

Only this round can catch: the summary strip, column ratios between panels, one
colour meaning one thing throughout, and what the page looks like before anything
is selected.

Repeat until the user ships it — or, when nothing on the page is worth changing,
say so **in the page's own terms** and offer to ship: *"the page reads well as it
is — shall we call it done?"*, not a report on what passed. A clean page is the
goal, not a failure to find fault with.

## Component rules that are not obvious

| rule | consequence if ignored |
|---|---|
| **Pass an explicit `height=`** | `MirrorPlot` renders its iframe at height **0** — mounted, correct data, invisible |
| **Every `filters` entry needs a `filter_defaults`** unless another panel is guaranteed to have set it | The panel sits on **"Loading…" forever** and the gate used to score it a pass. Pick a default useful on arrival — and check whether capture handed you a hint: a hardcoded selection in the notebook's plotting cell (`exp[12]`) tells you *what the author wanted seen first*, and that intent belongs here rather than on the config page. Carry the intent, never the literal — `exp[12]` is an index into their development file. **A default on a data-dependent identifier must be computed from this run's data** (`df.loc[df.score.idxmax(), "psm_id"]`), never a literal id carried over from a development dataset — an id absent from the user's run filters to nothing and loads forever, which is the failure this rule exists to prevent. A literal is only safe for a value the schema guarantees, such as the `observed` / `theoretical` sides the tool emits every time |
| **`filters_top` / `filters_bottom` must use disjoint identifiers** | `ValueError`. To drive both halves from one selection, publish the column twice: `interactivity={"psm_top": "psm_id", "psm_bottom": "psm_id"}` |
| **Pin a constant per side** with an identifier nothing sets, plus `filter_defaults_*` | How one long-format table feeds both halves: filter on `side`, defaults `observed` / `theoretical` |
| **Budget the header text, not the column count** | No column count is the right rule — a six-column table still truncated `Matched i…`. Fit depends on the header text, the font, and the width you assigned. Widths summing over the content width (~640px at 1280px with the sidebar open) also make Tabulator wrap onto a phantom second row. `verify-webapp-usability` measures the real property and fails on it; shorten a long header rather than widening its column |
| **Normalise per side before a mirror plot** | The halves share one symmetric axis; raw counts (~7e4) against theoretical intensities (~1) flatten one onto the baseline |
| **`highlight_column` is what makes annotations appear** | Without it, `annotation_column` labels nothing |
| **Insight caches by config hash** under `cache_path` | A stale cache serves the previous configuration. Clear it when a config change appears to do nothing |

`SequenceView` matches fragments inside the component from `sequence_data` +
`peaks_data` — do not precompute them.

## Style contract

Enforced by `verify-webapp-usability`.

- **Layout** — a summary strip of 3–5 headline numbers first; no panel taller than
  the viewport; column ratios follow panel role, never a default even split.
- **Semantics** — one colour per concept in every panel. **No raw column name
  reaches the user**, in either place it can: table column `title`s *and* plot
  axis labels (`mz` → `m/z`, `rt` → `Retention time (s)`). A reader given this as
  "axis labels carry units" renamed the table headers and left the mirror plot's
  axes as they came.
- **States** — nothing-selected shows an instruction; no-results-yet names the Run
  page; a traceback never reaches the UI. Write these first: they are the only
  thing on screen until a run finishes.
- **Theme** — primary, secondary and font in `.streamlit/config.toml`.

## Common mistakes

- Reloading the browser after editing a `src/` module. Restart the server.
- Debugging a blank panel by guessing. Print the selection state and filter the
  parquet with `filter_and_collect_cached` — that separates data from render in one
  step.
- Putting a number in both the summary strip and a table column.
