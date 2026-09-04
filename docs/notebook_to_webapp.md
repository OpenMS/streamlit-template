# From notebook to web app

Turn a Jupyter notebook into a working OpenMS web app by describing what you
want. This walkthrough converts the EuBIC winter-school identification notebook
(`EUBIC_Task2_ID.ipynb`) into an app with a configuration page you chose and a
results dashboard you designed.

**Time:** about 30 minutes. **You need:** a notebook, an agentic terminal (Claude
Code, Codex, Gemini CLI), and a Python 3.10+ environment. If you have none, `uv`
is enough — the framework finds whatever is there and tells you what it picked.

---

## What you are building

```
notebook cell                    becomes

  digest, search, score    ->    src/python-tools/identify.py
                                 a script with no Streamlit, tested on its own

  the constants in it      ->    a configuration page you designed

  the mirror plot          ->    a results dashboard where clicking a
                                 peptide shows its annotated spectrum
```

---

## 0. Start

Go to the **Quickstart** page of this app, copy the prompt under *Turn a Jupyter
notebook into an app*, and paste it into your terminal. It works from anywhere —
it will ask you where the notebook is. Nothing else is needed — the prompt clones the template and
points the agent at the framework.

**Checkpoint:** it names the Python interpreter it found, and a temporary folder
it cloned into — the app is not named yet, so the folder gets its real name in the
next step.

---

## 1. Choose, analyse, name

Three quick exchanges before any real work starts.

It asks for the path to your notebook — it does not go looking through your
folders. Then it reads that notebook, **without running it**, and tells you how it
read your analysis:

```
EUBIC_Task2_ID.ipynb — here is how I read it:

  loads an mzML and a FASTA                  ->  Upload page
  digests the proteins                       ->  the analysis
  generates theoretical spectra              ->  the analysis
  matches them to the measured spectra       ->  the analysis
  plots one mirror spectrum                  ->  Results page
  a tolerance exercise at the end            ->  dropped, but I'll reuse
                                                 the numbers it printed

Look right? Then I'll run it once and come back with what needs deciding.
```

Rows are steps of your analysis, not cells — you should not have to count cells to
follow your own notebook. No row counts and no runtimes appear here, because
nothing has been executed yet. Ask if you want it cell by cell.

Then it asks what to call the app. Everything else is derived from your answer —
the folder (the temporary clone is renamed now, before the app is ever launched),
the workflow class, the slug, the page titles — so this is the one name you pick
and it is picked once.

**Checkpoint:** the app folder is named after your app, and you have seen what it
thinks the notebook does.

---

## 2. Capture

The notebook is executed once, unmodified, and the reading is checked against what
actually ran. You see progress, not bookkeeping:

```
Running it once for reference numbers... (3.9s)
Extracting the analysis... testing it against your notebook... 7/7 OK
```

Executing first is the point: the numbers the notebook printed become the test
the extracted script must reproduce. Here that is 473 peptides, 1887 MS2 spectra,
and five specific peptide-spectrum matches.

**Checkpoint:** `src/python-tools/identify.py` exists and its test passes. The
script imports no Streamlit — you can run it from a terminal.

---

## 3. Review

Two batches, each arriving **already decided** — every row carries the
recommendation the framework would act on, so your job is unticking, not choosing
from a blank page.

**Shortcuts and suspicious constants** — code written for teaching, not analysis.
Each one quotes your line, says where it is, and says what it would do:

```
Your notebook analyses only the first 5 of 1887 spectra — `candidate_df.head(5)`,
cell 20. Remove that for the app?        (recommended: yes — the full run takes 4 s)

The sort just above it, `candidate_df.sort_values(...)`, throws its result away,
so head(5) takes the first five spectra and not the top five. Remove it?   (yes)

`relative_tolerance=0.1`, cell 19: np.isclose reads that as 10%, roughly ±169 Da
on a typical peptide, where MS works in ppm. Deliberate, or a typo?   (10 ppm)
```

**Config parameters** — the whole list, ranked by where each value came from in
your code, with the ones a mass spectrometrist would expose already ticked:

```
These are the settings I'd give the app's users.
Untick anything you'd rather fix at the notebook's value.

  [x] precursor mass tolerance   10 ppm     main specificity control
  [x] fragment mass tolerance    0.05 Da    same, at the MS2 level
  [x] missed cleavages           2
  [x] peptide length             6-30
  [ ] enzyme                     Trypsin    rarely changed per run
  [ ] fixed modifications        none

  The two tolerances interact — if you keep one, keep both.

  Want me to measure how much each one actually moves the result
  before you decide? (~90 s)
```

That last offer is optional on purpose. Measuring every parameter properly is
quadratic — a dozen of them is minutes, forty is hours — and it is only ever
needed to justify *hiding* something. **An unmeasured setting can be shown, never
hidden**: showing one that turns out not to matter costs a row on a page, hiding
one that does costs you something you cannot see was taken.

The two tolerances are why that rule exists. Swept on its own the absolute
tolerance moves the result by 0.7% and looks useless — because the relative
tolerance opens a window 1700 times wider and swamps it. A tool that measured one
parameter at a time would tell you to hardcode the most important setting in your
notebook. Ranking by where the value came from puts it first without measuring
anything at all.

Fixing that tolerance is also what makes the app practical: at 10 ppm the search
runs over all 1887 spectra in under a second and identifies 94 of them — instead
of five spectra carrying 57 spurious candidates each. That 94 is the number the
results page reports.

**Checkpoint:** `DEFAULTS` reflects your decisions and the tests still pass
against re-derived values.

---

## 4. Design the pages

Now the shape changes. From here the framework stops presenting tables and starts
**building things with you, one at a time**. Every round works the same way:

> it puts something on screen **in your own browser**, offers up to three
> suggestions — one about the **data**, one about the **layout**, one about the
> **behaviour** — plus a field for your own idea, and an exit.

One suggestion per axis, deliberately: three variations on the same idea would
not be a choice. And **three is a ceiling, not a quota** — every suggestion has to
point at something you can see on screen, so if only two axes have anything real
to say you get two, and if the page is already good you get told so and offered
the exit. The one exception is the very first panel: it has nothing to link to
yet, so its behaviour suggestion is a promise about a panel still to come, and it
says which one.

Before the first round it runs your app once end to end with your notebook's own
data — upload, configure, run, results — so nothing you are asked to look at is
empty or broken. Then it opens your browser on it.

```
Starting the app and doing a test run with your notebook's own data...
  upload -> configure -> run -> results    OK (11s)

Your app is running at http://localhost:8501 - opening it now.
```

The Upload and Configure pages come first. Here is one round on Configure:

```
[your browser, on the Configure page]

  A  data       Order the parameters the way they matter — precursor
                tolerance outranks missed cleavages, but sits below
                it on screen
  B  layout     Seven inputs in one column reads as a form. Two
                columns fits without scrolling
  C  behaviour  Save these values as a preset called "Notebook
                defaults", so there is a way back

  D  something else — tell me

  or: looks good, next
```

Pick one, and it re-renders and asks again. Take the exit whenever you are happy.
**The Upload page works identically** — the same three axes, asking about file
types, grouping, and what the page shows before anything is uploaded.

**Checkpoint:** `streamlit run app.py` starts, and Configure looks the way you
chose.

---

## 5. Design the dashboard

Same rounds, now per panel. First the link graph and a wireframe, before any code
exists:

```
 psms.parquet          -> Table        click sets 'psm'
 mirror_peaks.parquet  -> MirrorPlot   filters on 'psm'

 +--------------------------------------------------+
 | Peptide-spectrum matches            (Table)      |
 +--------------------------------------------------+
 | Spectrum match                 (MirrorPlot)      |
 |   observed above / theoretical below             |
 +--------------------------------------------------+
```

Then one panel is built, and you get a round on it:

```
[your browser, showing the match table]

Panel 1 of 2 — the match table.

  A  data       Show the charge column — you have it, and it explains
                why two matches score differently
  B  layout     The "Matched intensity" header is cut to "Matched i…"
                at the width this column has — shorten it, or take
                40px from the score column
  C  behaviour  Make a row click select the match, so the mirror plot
                below follows your selection

  D  something else — tell me

  or: looks good, next
```

Notice that C names the panel it is preparing for. The first panel has nothing to
link to yet, so a behaviour suggestion there is always a promise about something
you have not seen.

**Checkpoint:** clicking a row in the table changes the spectrum below it.

---

## 6. The last round

When every panel is approved, the page is exercised in a real browser before the
final round — it boots, the console is clean, every panel rendered, nothing sits
stuck loading, and clicking a row moves the panel linked to it. You never see that
check run. You see what it found, as the last round:

```
  A  data       Summary strip on top: 94 identified · best score 30 ·
                median 13
  B  layout     The mirror plot is taller than the fold; 520px puts
                both panels on one screen
  C  behaviour  Nothing is selected on arrival, so the mirror plot is
                empty — default to the top-scoring match

  D  something else       or: ship it
```

This step is not optional theatre. Streamlit's own test tools execute no
JavaScript, so a dashboard whose every panel fails to render passes them
completely. And the page is *looked at*, not only asserted on, because no
assertion catches a truncated column header or half a mirror plot flattened onto
the baseline — both real defects from building this app, both invisible to every
check above.

**Checkpoint:** the page works, and you have signed off on how it looks.

---

## What you end up with

```
eubic-id-app/
  src/python-tools/identify.py     tested, Streamlit-free processing
  src/IdentificationWorkflow.py    upload / configure / run / results
  src/dashboards/identification.py the linked panels
  content/identification_*.py      four pages
  tests/test_identify.py           your notebook's own numbers
```

The processing step runs from a terminal, in the app, or on a queue, and it is
the same code in all three.

## If a stage fails

Each stage leaves its artifact behind, so you can rerun one without redoing the
others. `interview-parameters`, `build-insight-dashboard` and
`verify-webapp-usability` all work standalone against an existing app — you can
point the dashboard builder at a results page you wrote by hand.

## Going further

- Add a second notebook: paste the prompt again inside the app; it adds another
  workflow rather than merging into the first.
- Change your mind about a panel: ask for another round on it.
- Change your mind about a parameter: rerun `interview-parameters`.
- Deploy: see the Deployment and Kubernetes guides.
