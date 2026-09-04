# OpenMS Streamlit Template

The framework for building mass spectrometry web applications, and for deriving
them from Jupyter notebooks. This file fixes the vocabulary; it is a glossary,
not a design document.

## Language

### Already overloaded — use these senses only

**Workflow**:
A `WorkflowManager` subclass and its slug, owning an upload/configure/execute/results
cycle inside a workspace. Never use this word for a notebook's analysis, for a CI
pipeline, or for the sequence of skills that builds an app.
_Avoid_: pipeline, process, job

**Parameter**:
Unqualified, this word is ambiguous — the template has three unrelated parameter
systems. Always qualify it: *simple-page parameter* (`default-parameters.json`),
*TOPP parameter* (`:1:`-prefixed, from an `.ini`), *python-tool parameter* (a
`DEFAULTS` entry), or *config parameter* (see below).
_Avoid_: setting, option, knob, argument

**Feature**:
In OpenMS file formats, a 2D isotopic peak cluster in a single run. In
OpenMS-Insight, the row identity of a quantification matrix. Name the sense
whenever both could be meant.
_Avoid_: analyte, entity

### Deriving an app from a notebook

**Entry prompt**:
The fixed natural-language text a user copies from the application and pastes into
their agentic terminal. It clones the template and points the agent at the
orchestrator skill *by file path*, because a repository cloned mid-session brings
its skills onto disk but not into the running session's skill registry — and
because terminals other than Claude Code have no skill registry at all.
_Avoid_: bootstrap, installer, one-liner, magic prompt

**Source notebook**:
The Jupyter notebook an application is derived from. It is read, never modified.
_Avoid_: input notebook, original, source file

**Capture**:
The act of deriving an application's analysis from a source notebook. Distinct
from copying it: capture classifies, isolates and verifies.
_Avoid_: conversion, port, migration, translation

**Cell class**:
What a source notebook cell is for — one of *setup*, *input*, *processing*,
*visualization*, *exercise*, or *demo shortcut*. Every code cell gets exactly one.
_Avoid_: cell type (that already means code/markdown/raw), category, kind

**Demo shortcut**:
Code present only to make a teaching notebook fast or short — a truncation applied
after a filter, a hardcoded plot window, a limit justified by a "for this tutorial"
comment. It is not analysis and must never reach an application unexamined.
_Avoid_: hack, stub, simplification, placeholder

**Golden value**:
A reference measurement taken from executing the source notebook, against which
the captured processing step is tested. Distinct from a fixture, which is input.
_Avoid_: baseline, expected value, snapshot, reference output

### The generated application

**Processing step**:
The analysis captured from a source notebook, as a single script that imports no
Streamlit, receives its configuration as JSON, and communicates only through files.
Realized as a python tool.
_Avoid_: backend, kernel, engine, core, business logic

**Output contract**:
The processing step's static declaration of what it produces — each file, its role,
and the identifier it can be linked on. Read without executing anything.
_Avoid_: manifest, schema, result spec, interface

**Config parameter**:
A value the application's *end user* can change, surfaced on a configuration page.
The outcome of a parameter interview; a notebook constant that stays fixed is not
one.
_Avoid_: exposed parameter, tunable, user parameter

**Panel**:
One visualization region on a results page, bound to one output and one component.
The unit of dashboard construction and of dashboard review.
_Avoid_: widget, chart, plot, tile, card, block

**Link identifier**:
The shared name through which panels communicate a selection — set by one panel,
consumed as a filter by others.
_Avoid_: selection key, link key, cross-filter, join key

**Style contract**:
The checkable appearance rules a results page must satisfy — colour semantics,
axis labelling, empty states, layout limits. Enforced, not advisory.
_Avoid_: style guide, design system, conventions

### The framework itself

**Browser control**:
Driving a page — screenshotting it, clicking it, reading its DOM. Distinct from
**opening** a page, which needs nothing at all. Control needs two pieces: the
Claude browser extension, installed by the user in their own browser under their
own claude.ai account, and a native messaging host that Claude Code registers
itself. Only the first is ever the user's to do.
_Avoid_: browser access, Chrome integration, headless browser

**The attached browser**:
The browser the extension answers for. Attached is not theirs: it may be a
window nobody is sitting at, and a run drove one for a whole preflight while
the user was asking what it was looking at. Where it runs is a property of the
deployment, never a fault to diagnose. One thing earns it their app — that it
loads a page this host serves **on loopback**. Nothing available proves a human
is in front of it, so the framework does not claim that and does not measure it.
_Avoid_: their browser, the local browser, the Chrome instance

**The marker**:
A token of at least ten characters, served from this host on `127.0.0.1` and
read back out of the page body in the browser under control. The single
instrument that separates a browser which can load what you serve from one that
merely answers. Its verdict is reach, never presence and never location: a
token returned proves the pair works, not where either end is.
_Avoid_: the test page, the handshake, the ping, the reachability check

**The decline**:
An explicit no to the browser ask. It is the only thing that licenses a run to
judge its own pages in the gate's headless browser instead of the user's
window. Silence is not a decline; neither is moving on to the next question.
_Avoid_: no control, the fallback, going without

**Control unreachable**:
Control that answers and drives pages, attached to a browser that cannot load
what this host serves on loopback. Its `localhost` is not this machine's, so it
renders whatever sits on that port over there — convincingly, and as though it
were the app under construction. Nothing in the tab context distinguishes it; a
page you serve does. A property of the pair, never a verdict on the browser.
_Avoid_: control foreign, wrong browser, broken control, not connected

**Control lost**:
Confirmed control that has silently stopped being true. The user closes their
browser, the device leaves the account's list on its own, and the session is
re-attached to another one without a word — after which `navigate` keeps
returning success on a screen nobody is watching. It fails in the success
direction, which is why no return value detects it and why the repair is the
user reopening their browser rather than anything the run can do alone.
_Avoid_: disconnected (that is a different failure), the browser crashed, stale control

**Control absent** vs **control disconnected**:
Two failures that look alike and are not. *Absent* is the browser tools having no
schema in this session: there is no probe to run, launching a browser cannot
create one, and a session started afterwards is what picks them up. *Disconnected*
is the tools loading and reporting that nothing answers — the browser is shut, or
the extension is missing from it — and that one is fixable where you stand.
_Avoid_: not connected (for both), browser not working

**Stage skill**:
One of the skills performing a single stage of app derivation, invocable on its own
against an existing application.
_Avoid_: sub-skill, step, module, phase

**Interview**:
A single batch review pass in which the framework presents its findings with
recommendations and the user decides each row. Not a series of questions. Used
where the framework has *measured* something or has a defensible opinion, and the
user is adjudicating it — findings, config parameters, which template pages to
keep. It arrives **already decided**: every row carries the recommendation the
framework would act on, so the user's work is unticking rather than choosing from
nothing. Contrast with *design round*.

An interview is **asked, never drawn**. A checklist rendered into the transcript
is a decision the user cannot make: they would have to retype it to answer. Rows
reach them as options they select. Where there are more rows than one screen of
options holds, the interview asks whether the recommendation stands before it
asks about any single row.
_Avoid_: wizard, questionnaire, prompt, survey

**Design round**:
A single exchange of co-design: the framework renders something, **puts it in the
user's own browser**, offers up to three suggestions and a free field, applies the
user's choice, and re-renders. Used where there is nothing to measure and the
decision is taste. Repeats until the user exits; the exit is always offered.
Contrast with *interview*, which happens once and decides many rows at a time.

Rounds on **Results** may propose anything the panels can express. Rounds on
**Upload** and **Configure** are bounded by *template functionality*: those pages
have a shape the template already chose. Suggestions arrive **one at a time** —
three at once is not a choice, it is a pile.
_Avoid_: iteration, refinement loop, review cycle, feedback round

**Suggestion axis**:
The aspect of a page a suggestion addresses — *data* (what is shown or accepted),
*layout* (how it is arranged), or *behaviour* (what happens when the user acts, or
has not acted yet). A design round offers **at most one** suggestion per axis — so
where it offers several they are real alternatives rather than phrasings of one,
and where an axis has nothing grounded to say it is named clean instead.
_Avoid_: category, dimension, theme, bucket

**Template functionality**:
The surface a design round on Upload or Configure is allowed to touch: the
arguments the template's own widgets already accept — `upload_widget`'s `name`,
`file_types` and `fallback`; `input_TOPP` / `input_python`'s `custom_defaults`,
`advanced`, `help`, `widget_type`, `display_subsections`, `display_tool_name`,
`tool_instance_name` — plus section naming, section order, and named presets in
`presets.json`. A suggestion that reaches for a layout primitive the page does
not already use is out of bounds: the template decided that, not this app.
_Avoid_: allowed changes, scope, the knobs

**Feasibility pass**:
The reasoning a suggestion goes through **before** it is shown — resolving it to
the specific file and edit that would implement it. A suggestion whose edit
cannot be named is dropped rather than offered, and one whose edit turns out
smaller or larger than it sounded is reworded to match. Its purpose is that the
framework never has to walk a suggestion back after the user has accepted it.
_Avoid_: sanity check, validation, review

**User-facing turn**:
Everything the framework prints between one user input and the next. The unit the
output budget applies to: **200 words**, because a reader who has to take in more
than that at once stops reading and starts skimming. Thinking is not part of it —
the budget constrains what is shown, never what is worked out.
_Avoid_: message, response, output, turn (unqualified)

**Progress line**:
One short statement that a slow action is under way or has finished, naming the
action and nothing about how it works — *"Running it once for reference
numbers…"*. What replaces a report when there is no decision attached. A progress
line is not a place to put evidence.
_Avoid_: status update, log line, narration

**Register**:
The rule that the framework talks like a mass spectrometrist, never like its own
implementation. Cell classes, harvesting, probes, sweeps, gates, screenshots,
`DEFAULTS` and `OUTPUTS` are how the work is done and never appear in a
user-facing turn. The user's own vocabulary — spectra, tolerances, peptides,
pages — is what remains.
_Avoid_: tone, voice, style (that is the *style contract*, which is about pixels)

**Smoke run**:
One complete pass through a generated app — upload, configure, execute, results —
driven by the framework with the notebook's own data, before the user is asked to
look at anything. It is what makes a design round possible: a page with no data
in it cannot be designed against.
_Avoid_: test run, dry run, sanity check

**Usability gate**:
The browser-driven check a results page must pass — hard assertions plus a
screenshot critique. A gate, not a report: it can fail. **Internal**: its findings
reach the user rephrased as design suggestions, and the gate itself is never
mentioned.
_Avoid_: smoke test, UI test, visual check

**Persona**:
A scripted user the self-improvement loop plays in order to measure the interviews
rather than only the generated code. One of them, the **clicker**, types exactly
two things in the whole session — the notebook's path and the app's name — and
selects everything else. Any decision the clicker cannot reach is a decision that
was drawn instead of asked.
_Avoid_: mock user, actor, simulated user, role

**Judge**:
The model that reads two persona transcripts of the same task, without being told
which came from the edited skill, and says which one guided the user better and
why. It never assigns an absolute score.
_Avoid_: evaluator, grader, rater, critic

**Pairwise verdict**:
The judge's preference between the transcripts before and after a skill edit,
counted across personas. It is the loop's keep-or-revert signal for guidance, and
its stated reason is the lead for the next tick.
_Avoid_: rubric score, guidance score, rating, win rate

**Tick**:
One iteration of the self-improvement loop: evaluate the corpus, make a single
skill edit, re-measure, keep or revert. Not a *design round*, which is the user
improving their own app.
_Avoid_: round, cycle, epoch, run
