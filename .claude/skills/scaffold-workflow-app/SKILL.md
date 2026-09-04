---
name: scaffold-workflow-app
description: Use when wiring a python tool into an OpenMS Streamlit app, when creating a WorkflowManager subclass and its upload/configure/run/results pages, or when a new workflow must be registered in app.py and settings.json.
---

# Scaffold a workflow app

Wire a processing step into the TOPP Workflow Framework: a `WorkflowManager`
subclass, four content pages, registration, and app identity.

The route for a **captured python tool**. For a workflow chaining TOPP tools use
`create-workflow`; for a standalone page, `create-page`.

## The rule

**`execution()` is annotated `-> bool` and returns `True` only when every step
succeeded, and every `run_topp` / `run_python` call is gated on its return value.**

Both callers write the `WORKFLOW FINISHED` marker from that return value, and the
marker is the only thing the Run page reads. Returning `None`, or ignoring an
executor result, reports a run whose third tool died as a success.

## Files

```
src/<Name>Workflow.py            WorkflowManager subclass
src/python-tools/<name>.py       the processing step (from capture)
src/dashboards/<name>.py         results rendering (from the dashboard stage)
content/<name>_file_upload.py    4 thin pages, one call each
content/<name>_parameter.py
content/<name>_execution.py
content/<name>_results.py
tests/test_<name>.py             golden values
```

Each page is four lines: `page_setup()`, construct the workflow, call one of
`show_file_upload_section()` / `show_parameter_section()` /
`show_execution_section()` / `show_results_section()`.

**`<name>` is one stem**, derived from the app name and used in every file above —
not a free choice per file. It also appears as a **string literal** in
`input_python("<name>")` and the tool argument to `run_python()`, so a rename
touching only filenames leaves those dangling. Measured: the golden tests still
pass 7/7 and every module parses, because the tests run the tool as a subprocess
and never construct the workflow — then the app throws an `stException` on the
**Configure** page. No test in the generated app catches it, and the reason is
worth knowing: `test_gui.py` names the pages it launches **by hand**
(`test_gui.py:22-36`), and that list still holds the template's pages. Unless the
four new pages are added to it, the suite launches pages the app no longer
registers and never launches the ones it does. **Add yours and remove theirs**,
in the same edit that hides the pages from `app.py` — the list has two halves and
fixing one is not fixing it. Measured on a real build: the four new pages were
added and the hidden template pages were left behind, so the suite passed while
launching three pages the sidebar no longer offers. Until then only opening the page can catch this. After any
rename, grep for the old stem and expect zero hits outside comments.

## Dependencies

**An app declares what it imports.** Anything the generated code imports that the
template's own `requirements.txt` does not already list goes into the app's,
pinned. The template stays as it is — it is a template, and the app is what has
the dependency.

Measured: two consecutive builds shipped apps whose dashboard did
`from openms_insight import ...` while their `requirements.txt` never mentioned
it. Both ran, because the venv on that machine already carried the package; a
clean `pip install -r requirements.txt` of either produces an app that dies on
import. Three earlier apps carry the line, so this is something that stopped
happening rather than something never done.

## Non-negotiables

Each is a way to produce an app that looks fine and is broken.

- **`page_setup()` runs before the workflow is constructed.** The constructor
  dereferences `st.session_state["workspace"]`, and upload widgets need
  `location` / `previous_dir` / `local_dir`, which `page_setup()` sets.
- **Decorate `configure()` and `results()` with `@st.fragment` — both, every
  time.** Without it, a widget inside the method reruns the whole page script
  instead of the method: `page_setup()` again, the workflow constructed again,
  every panel redrawn. On Results that is the difference between clicking a table
  row and redrawing one panel, and clicking a table row and rebuilding the page.
  It is the only bullet here whose damage is invisible in a screenshot — the page
  looks right, it is just wrong to use. Measured: 1 build in 4 decorated
  `configure()` and forgot `results()`, and every test still passed. The
  template's own example decorates both (`src/Workflow.py:29` and `:119`).
- **`input_python()` requires `st.session_state["advanced"]`**, created only by
  `parameter_section()` — calling it elsewhere raises `KeyError`.
- Nothing reachable from `execution()` may touch `st.session_state`. Online
  mode runs it in an RQ worker that has none; worker and UI share state only
  through the workspace filesystem.
- Guard the user's selection before `get_files()` — it raises `ValueError` on
  an empty list.
- Choose the workflow slug once. It is load-bearing in three places at once
  (workflow directory, `presets.json` key, every session-state prefix); renaming
  orphans presets and abandons existing parameters.

## Registering

Add a section to the `pages` dict in `app.py`, and set `app-name`,
`repository-name`, `github-user` **and `version`** in `settings.json`.

`version` is the one field that arrives already wrong. The clone inherits the
template's own version, so a brand-new app introduces itself in the sidebar at
whatever release the template happens to be on — a first-ever run reporting
`1.1.1` claims a history it does not have. Set it to `1.0.0`. It is the user's
app now, and this is its first version. Python-tool parameters do
**not** go in `default-parameters.json` — that belongs only to the simple-page
system.

## Clearing the template's pages, and rewriting Documentation

**Open `cleanup.md` now** — when you are about to edit `app.py` or `content/documentation.py`, its rules are there and
not here. It is a few hundred words and it is the difference
between remembering this section and having it in front of you.

## The smoke run, and handing the app over

**Open `handover.md` now** — when the app boots and you are about to show it to anyone, its rules are there and
not here. It is a few hundred words and it is the difference
between remembering this section and having it in front of you.

## Design rounds on Upload and Configure

**Open `rounds.md` now** — when you are about to put a page in front of the user and ask what they would change, its rules are there and
not here. It is a few hundred words and it is the difference
between remembering this section and having it in front of you.

## The template's code is not yours to change

A generated app is a **clone**, and clones get merged with upstream. So
`src/workflow/`, `src/common/` and the template's own `tests/` are code you have
inherited, not code you own. Changing them there is not a local fix: every future
rebase carries it, and nobody reviewing the app sees a diff against the template
that was supposed to be identical.

**The page list in the root `test_gui.py` is not in that set.** `tests/` above
means the directory; `test_gui.py` is a root file and a different suite, and its
hand-written list is the app's page registry written out a second time. It
changes when the registry changes — adding yours and removing the template's is
required above, and it is not a template edit. Read the two rules together and
this is the seam between them.

There is exactly **one** sanctioned edit in that area, and it is named in Common
mistakes below: `run_python()` spawning `sys.executable` instead of the literal
`"python"`. Everything else is a finding, not a task.

**When the template looks wrong, say so and route around it.** Report the
symptom, the file and the line, and what it costs the user — then take the local
option. What you must not do is patch the shared module and then edit the
template's tests so they still pass: the tests are the only thing that would have
caught the change, so changing them to match converts a visible divergence into
an invisible one.

Measured on a real build. Asked to add a preset button, the framework found the
preset mechanism did not move an already-mounted widget, rewrote `apply_preset`
in `ParameterManager.py` from delete-keys to assign-values, adjusted
`StreamlitUI.py` to match, and then rewrote `tests/test_parameter_presets.py` so
the suite went green. The diagnosis was good. The two shared modules were the
wrong place to put it, and the test rewrite removed the evidence.

## Common mistakes

- Editing a `src/` module and expecting the running app to notice. Streamlit
  reruns the page script but does not re-import modules already in `sys.modules`.
  This costs more debugging time than anything else here: the app keeps reporting
  an error you already fixed.
- **A fork whose `run_python()` still spawns the literal `"python"`.** It must
  spawn `sys.executable` — the interpreter already running the app. *"Launch with
  the environment active"* was the standing advice here and **it does not work**:
  measured with the venv first on `PATH` and the parent process being that venv's
  own `python.exe`, the child still resolved to a different interpreter
  (`…/uv/python/cpython-3.12/python.exe`) and died on `import numpy`. Three
  variants of activating the environment made no difference; one line did.
  Generated apps are **full clones**, so fixing the template reaches none of the
  apps already produced — grep every `src/workflow/CommandExecutor.py` you own.
  This was found by the first end-to-end execution ever attempted, at tick 098,
  after ninety ticks of a corpus scoring 1.000 without it.
- Passing `input_output` keys the tool does not declare. They merge into the
  tool's parameter JSON; a typo becomes an unused key and the tool silently falls
  back to its default.
