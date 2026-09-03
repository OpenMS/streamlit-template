---
name: notebook-to-webapp
description: Use when someone wants to turn a Jupyter notebook into a web application, when a notebook analysis should become an OpenMS Streamlit app, or when asked to build an app from a notebook by describing it in natural language.
---

# Notebook to webapp

Turn a source notebook into an OpenMS Streamlit application. This skill owns the
ordering, the handoffs and the opening; each stage is a skill of its own that also
works standalone.

Most users arrive by pasting the entry prompt from the app's Quickstart page,
having never read any of this. Assume no knowledge of the template, of Insight, or
of the vocabulary.

Vocabulary: `CONTEXT.md`. Rationale: `docs/notebook-to-webapp-design.md`.

## The rule

**Run the stages in order, and never skip a review.**

Capture must execute the notebook before anything is extracted, or a faithful
extraction cannot be told from a plausible one. Shortcuts must be resolved before
parameters are probed, or every sweep measures a truncation instead of a
parameter.

**In order means by dependency, not by wall clock.** What a stage consumes is
what fixes its position: capture must execute before extraction, and shortcuts
must be resolved before parameters are probed. Work that depends on nothing
downstream may start early — the dashboard's link graph and wireframe read
`OUTPUTS` alone, so they can be drawn while the interview is still open, and only
the panels need a running app. Say so when you do it, and never let early work
become a reason to skip what it was waiting on.

**A user may accept every recommendation at once; they may not skip seeing them.**
*"Skip the interview, the parameters look fine"* is a waiver of something they
have not been shown — including the suspicious constants, which are the half of
that review they cannot guess at. Present it, and let them clear it in one word.

That is also the boundary against *never ask for what you can determine* below:
**determinable is not the same as yours to decide.** That a constant is suspicious
is determinable; whether it is a setting, a shortcut, or a defect is the user's.
Under pressure to skip ahead, this is the rule that gets crossed — a reader given
this skill collapsed the interview to "one pass, no interview" and cited the
determinable rule to justify it.

## What the user sees

**A user-facing turn is at most 200 words of prose.** Past that a reader skims,
and a skimmed recommendation is an unmade decision. The work is not what has to
shrink — classifying, probing, cross-checking, reading the screenshot all still
happen, in thinking. What reaches the screen is a **progress line** while
something slow runs, and an **interview** when something needs deciding. Between
those two there is nothing to say.

**One progress line per stage, not per step.** The stages are the five in the
table near the end of this file, and nothing else is one — a line goes out when
a stage starts, and the wording is whatever a user would recognise as a piece of
their own work: pulling the analysis out, building the app. The workflow class,
the page registration, the template cleanup and the three test lists are four
steps of *one* stage, and four lines saying so is the framework thinking out
loud:

```
Now pulling the analysis out into a script.        Now pulling the analysis out into a script.
Created eubic_task3_quant.py +376-0
Now the golden test against your numbers.          Verified it reproduces your notebook.
The extracted script reproduces your notebook.
Now the workflow class and its four pages.         Now building the app.
Now registering the pages and clearing the
  template's own.
Now test_gui.py — all three of its lists.
Now the Results page. Here's what I'd build:       Now the Results page. Here's what I'd build:
```

Eight lines against four. Note what the third one on the left is doing: *"all
three of its hand-written lists"* is a phrase out of `cleanup.md`, read aloud.
A step that only exists because this framework has a rule about it is not a step
the user is waiting on.

**A findings list is bounded by rows, not words: at most five.** The budget and
*"every question carries the thing it is about, quoted, and a recommendation"*
would otherwise contradict each other, and the second one wins: four constants,
each with the user's own line, its consequence and a recommendation, come to
about 240 words with every word working. A list is *meant* to be skimmed — the
reader scans for the row they disagree with — so prose stays under 200 and rows
are counted instead. Past five rows, the review is too big to
decide in one pass — put the five that matter and offer the rest.

**Talk like a mass spectrometrist, not like this framework.** Cell classes,
harvesting, sweeps, probes, gates, screenshots, `DEFAULTS`, `OUTPUTS`, masking —
all of it is how the work is done, and none of it belongs in a user-facing turn.
The leak is rarely a slip; it is an internal table shown verbatim — capture's
classification table has a *destination* column reading `code dropped, output
harvested`, written for an agent.

| what the framework calls it | what the user is told |
|---|---|
| harvested the exercise cell's output | your notebook already tested this — I'll reuse its numbers |
| the probe reports a fraction of a percent across the sweep | changing this barely moves the result |
| a `filter_defaults` value on the link identifier | which spectrum the plot opens on |
| took a screenshot of the Results page | *(nothing — open their browser instead)* |
| the gate found a truncated header | that column title is cut off |
| extraction reproduces the notebook — 7/7 golden checks pass | the extracted script reproduces your notebook |

**A number belongs in a user-facing turn only if it is theirs.** `7/7 golden
checks`, `233 tests pass`, `11/11` are the framework reassuring itself; *"the
same four peptides"*, *"<n> features"* are their own result handed back. This
holds in every turn, not only the last one.

**Every question carries the thing it is about, quoted, and a recommendation.**
Not a summary of the evidence — the specific line, the value, the cell. *"Your
notebook analyses only the first <n> of <total> spectra — `df.head(<n>)`, cell
<k>. Remove that for the app?"* is answerable; *"the truncation costs <delta> to
remove"* is a fact about a decision the user has not been shown. A question they
would have to go and look something up to answer gets answered *"whatever you
think"*, and that is not consent.

## Talking to the user

Two mechanisms, not interchangeable:

| | **interview** | **design round** |
|---|---|---|
| when | you measured something | there is nothing to measure |
| shape | one batch, many rows | one thing, repeated |
| user | adjudicates evidence | picks a direction |
| where | capture findings, config parameters | Upload, Configure, Results |
| how | options they select | one suggestion, then the next |

**An interview is asked, not drawn.** A checklist typed into the transcript is a
decision the user cannot make: to answer it they would have to retype it. Rows
reach them as options they select. Where there are more rows than one screen of
options holds, ask whether the recommendation stands **before** asking about any
single row — most of the time it does, and the whole list closes in one click.
Every row can be right and the whole thing still unreachable.

Six habits:

- Show it before you ask about it. A question about something the user cannot
  see is one they must imagine an answer to.
- Carry a recommendation into every fork. "I suggest X because Y" — not "what
  would you like?"
- **Never resolve a fork yourself and report it as applied.** The shape to
  refuse: a turn that says *"two calls before I build the config page"*, lays
  out the evidence for both, offers nothing to select, and is followed by
  *"Applied: … now defaults to 0, … to 20 ppm."* Every word of the evidence can
  be right and the user has still not decided anything — and the run then spends
  a later turn explaining the consequence of a value they never chose. Naming
  something a decision and then making it is worse than never raising it: it
  reads as consultation and works as an announcement. If it is genuinely yours
  to settle, settle it silently and say so once it is done; if it is theirs, it
  arrives with a recommendation and something to click.
- Report conclusions, not process. Name the interpreter you chose, not the
  five you probed. Name what needs attention, not how many things do.
- Never ask for what you can determine. Ask only what is genuinely the
  user's: the name, what belongs on the config page, how a page should look.
- **After every answer, say what is now under way.** A user who has just decided
  something is owed the consequence of deciding it. An answer followed by silence
  reads as the framework having wandered off, and the longer the silence the more
  it reads that way — the stretch after the app name is the longest in the whole
  run. One line, naming the next thing and the one after it: *"Right — pulling
  the analysis out into a script, then checking it still gets your notebook's
  numbers."* Without it the user is left guessing what is happening, and says
  so.

When a decision is rejected, re-derive it — do not restate it, and do not
simply adopt the correction. Restating repeats the call they rejected, louder.
Capitulating looks agreeable and is worse: they can be mistaken, and a framework
that folds on contact cannot be trusted when it agrees. Re-read the specific thing
named, report what changed *and what did not*, hold a disagreement with a line
number as evidence, then re-check whatever was decided by the same reasoning — a
misclassification is usually systematic.

## Opening

1. **Set up everything that needs setting up, before the first question.**
   Clone into a neutral folder — the app is not named yet — find a Python,
   install the dependencies, and confirm you can drive a browser. Probe order and
   the Windows Store-stub trap: `capture-notebook-workflow`.

   **Opening a browser and driving one are different capabilities, and only the
   second needs tooling.** Conflating them costs the user the thing they most
   want to see:

   | | needs | used for |
   |---|---|---|
   | **open** a page | nothing — `start <url>`, `open <url>`, `xdg-open <url>` | every design round, and the handover |
   | **drive** a page | browser control | the usability gate: screenshots, clicking, reading the DOM |

   So a page always opens. Saying "my browser extension isn't connected" instead of opening the page fails twice: it withholds the app, and it names this framework's plumbing to a mass spectrometrist.

   Browser **control** is not needed until the gate, but set it up here. An
   install prompt arriving mid-flow lands on a user who was in the middle of a
   decision, and asks a scientist to configure tooling for a framework they
   should never have had to see.

   **Preflight checklist, all of it before the first question:**

   1. Clone into a neutral folder — the app is not named yet.
   2. Find a Python and install the dependencies. Probe order and the Windows
      Store-stub trap: `capture-notebook-workflow`.
   3. **Open `connect-browser-control` now** — before the first question. It
      connects control and confirms it by driving a page this machine serves, or
      leaves the page checks to the headless browser. Its rules are there and
      not here.
   4. Install the gate's headless browser.

   Where the browser runs, what is checking what, and what you can or cannot see
   are this framework's plumbing, and none of it is something they can act on.
   **Never let any of it stop you opening their app**, which needs none of it.

   **This stage produces at most two user-facing turns, and no others:**

   1. Optionally one line saying you are setting up — *"Setting up — a minute,
      then I'll ask about your notebook."*
   2. **The install request, whenever step 3 earns one.** It is a click only
      they can make; `connect-browser-control` has its wording and the table
      that decides it. This turn is required when earned, and no rule on this
      page suppresses it.

   Nothing else: not the step list, not the word `preflight`, not the browser.
   *"Now preflight — Python, dependencies, and browser setup, before I ask you
   anything"* was measured in **10 builds of 19**, across fifteen wordings:
   *"Preflight — probing environment in parallel"*, *"Now the browser side of
   the preflight"*. Each hands a mass spectrometrist a list of this framework's
   own steps, and the word `preflight` means nothing to them.
2. **Ask for the notebook's path.** One question, no list. Do not scan the folder
   the prompt was pasted in, and never the clone's parent. A user who pastes a
   prompt into a working directory has not invited an inventory of it, and the
   parent scan reports their other projects back to them. Listing their notebooks and the webapps beside them reads as snooping.

   Reading the directory the user *names* is different, and stays — capture has
   to find the notebook's data files to pre-stage them.
3. Analyze statically, show the summary, and **wait for the user to confirm it
   before running anything.** Showing is not asking. This is a gate and it is
   separate from step 4: a reader who folds the two together presents the reading,
   asks for the app name in the same breath, and then executes — so the user is
   never given the chance to say the reading is wrong, which is the one thing
   every later stage inherits. Measured: **3 of 3 readers did exactly that** when
   this step said only "show the summary".
   Format and the no-numbers-yet rule: `capture-notebook-workflow`.
   Then run it, and **report the runtime from the trace, never from the code**:
   `<runtime>, over <n> of the <total> spectra`. You executed it; the count is a
   fact you hold, not one to infer from what a variable happens to be called.
4. Once the reading is confirmed, ask what to call it, then derive everything and
   show the derivation.

| from `UPS1 Quantification` | |
|---|---|
| folder, `repository-name` | `ups1-quantification-app` |
| `app-name`, `app.py` section | `UPS1 Quantification` |
| `WorkflowManager` subclass | `UPS1QuantificationWorkflow` |
| workflow slug | `ups1-quantification` |
| pages | `ups1_quantification_{file_upload,parameter,execution,results}.py` |
| python tool, dashboard, test | `ups1_quantification.py`, `test_ups1_quantification.py` |

Derive every row. The tool name is the one that bites — it appears as a **string
literal** in `input_python()` and `run_python()`, so renaming files leaves them
dangling. Measured: tests still pass 7/7 and every module parses, then the app
throws on the Configure page. Grep for the old stem afterwards.

Rename the clone before the app is ever launched. Workspaces live in
`../workspaces-<repository-name>`, and the slug owns the workflow directory, the
`presets.json` key and every session-state prefix.

## Stages

| # | skill | produces | review |
|---|---|---|---|
| 1 | `capture-notebook-workflow` | python tool with `DEFAULTS` + `OUTPUTS`, golden test, findings, prior evidence from exercise cells, any hardcoded selection | confirm the split |
| 2 | `interview-parameters` | shortcuts, then config parameters | interview |
| 3 | `scaffold-workflow-app` | `WorkflowManager` subclass, 4 pages, registration, template pages hidden, **smoke run** | rounds on Upload, Configure |
| 4 | `build-insight-dashboard` | link graph, wireframe, panels | round per panel |
| 5 | `verify-webapp-usability` | browser gate + screenshot critique — **internal** | feeds the final page round |

Announce each stage as a progress line — **except stage 5**, which has nothing of
the user's to name. Checking the page is not news, and what the check finds
arrives inside the round that follows. Do not say what the next stage will
consume either: that is a handoff between stages, and the user is not one of
them.

**No design round opens before the smoke run passes.** A round asks the user to
look at a page; a page that has never had data in it, or that throws, is not a
design question but a bug wearing one. Upload → configure → execute → results,
once, with the notebook's own data, then open their browser.

## Handoffs

Each stage consumes a **declared artifact**, never a conversation. The
producer is not always the preceding stage — capture feeds the dashboard
directly, and the gate feeds back into it:

- opening → capture: notebook path, chosen Python, app identity
- capture → interview: findings, `DEFAULTS`, and **prior evidence** harvested from
  exercise cells — sweeps the notebook already ran
- interview → scaffold: the resolved `DEFAULTS`, and the notebook's own resolved
  values as a named preset — `add-presets` owns `presets.json`
- capture → dashboard: `OUTPUTS`, read without running anything, plus any
  **hardcoded selection** from a visualization cell, as a proposed
  `filter_defaults` rather than a config parameter
- dashboard → verify → dashboard: panel count, then gate findings as material for
  the final round

If a stage needs something the previous one did not declare, that is a defect in
the earlier contract. Fix it there.

## Non-interactive mode

Every stage supports `mode=auto`: take the recommendation and the first
suggestion, never block. For the self-improvement loop and scripted personas only
— a human-facing run always shows every review.

## Adding a second notebook

Run the orchestrator again inside the app. One notebook produces one workflow; a
second adds another rather than merging.

## Common mistakes

- Quoting numbers in the analysis summary before the notebook has run.
- Naming the app for the user because they paused.
- Renaming the folder after the first launch — it strands the workspace.
- Running a design round on a page the user does not have open.
- Reporting success from a green gate without opening the screenshot.
- **Showing an internal table because it was already written.** Every register
  leak so far has been an agent-facing table — a classification, a probe result,
  a gate report — pasted rather than translated.
- **Narrating the machinery.** "Taking a screenshot", "running the gate",
  "starting the masking re-probe" describe the framework working, which is not
  news. The progress line names the *user's* thing: their notebook running, their
  app starting.
- **Slipping into instrument language when something goes wrong.** This is where
  the rule above actually breaks: a build that hit a page error narrated its own
  investigation four turns running — *"a JS page error the gate reports as
  `undefined`"*, *"both come from the table iframe as unhandled Tabulator promise
  rejections"*, *"let me look at the screenshot before I show you the page"* —
  every one of them a status line, none of them a finding. Trouble is still
  user-facing, and the register does not change: they hear what is wrong with
  **their page**, never what your instrument reported. If the fault has no
  user-visible symptom yet, that is a reason to say less, not to describe tools.
  **The template's own source is machinery too.** A later build explained a
  preset that would not refresh as *"`StreamlitUI.preset_buttons` →
  `ParameterManager.apply_preset:661` clears the widget state, and widgets
  generated from a Python tool don't pick that up"*. The decision behind it was
  right — it moved the button rather than patching shared code — and the
  sentence still handed a mass spectrometrist two class names and a line
  number. What reaches them is the symptom and the choice: the numbers did not
  change until the page reloaded, so the button now lives in their workflow.
- **Drawing a decision instead of asking it.** Tick-boxes, arrows and numbered
  recommendations printed into the transcript. Everything the user is meant to
  decide arrives as something they can select.
- **Stacking suggestions.** Three at once is not a choice, it is a pile. One,
  then the next.
- **Offering a change you have not costed.** A suggestion is resolved to its edit
  in thinking before it is shown, or it is not shown.
- **Asking for an install after the run has started.** Everything installs in
  step 1.
