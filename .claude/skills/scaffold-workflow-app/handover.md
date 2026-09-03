# The smoke run, and handing the app over

Part of `scaffold-workflow-app`. Read this when the app boots and you are about to show it to anyone.

Before the first design round, drive the whole app yourself once: upload the
notebook's own input files, take the resolved defaults, execute, open Results.
Then start the user's browser on it — `start <url>` / `open <url>` /
`xdg-open <url>`. No browser tooling is involved; that is only needed to *drive*
a page, and the gate is the only thing that drives one.

A design round asks someone to look at a page and say what should change. A page
that has never held data, or that raises on arrival, is not a design question but
a bug wearing one, and the round gets spent on it. Every panel rule in
`build-insight-dashboard` assumes something rendered.

Report the outcome in one line, not the steps in four:
`upload → configure → run → results   OK (<runtime>)`. If it fails, fix it before
opening the browser — the user never needs to know a round was waiting on it.

### Restart, then smoke-run again, before you hand over

Streamlit imports a `src/` module once per server process and never again. Every
later edit — a design round applying a change, a dashboard panel, a fix to the
tool — leaves the running server holding the **old** module object while a new
one sits on disk. Two things break, and only one of them is visible to you:

- the page renders the unchanged version, which you will notice within seconds;
- **`Run` raises `PicklingError: <class '…Logger.Logger'> … is not the same
  object as …Logger.Logger`**, which you will not, because the workflow only
  spawns a process when someone clicks Run. On Windows that spawn pickles the
  manager, pickling checks that each class still matches the one importable at
  its own path, and after a reload two versions of that class exist. The app the
  user opens is the app that crashes on the first thing they do with it.

So the **last** action before handover is: stop the server, start it again, and
drive the smoke run once more on the restarted process. A smoke run from before
the final `src/` edit is evidence about a different app.


### The closing turn

The last thing they read is short, and it celebrates:

```
🎉 Your app is ready!

  ..\.venv\Scripts\python -m streamlit run app.py

✅ It reproduces your notebook's numbers — same features, same peptides.
```

Someone has just watched their notebook become an application. Say so like it is
good news. A couple of emoji at the end are worth more than a paragraph of
detail: they mark the ending as an ending, which a wall of facts does not. Two or
three, not a row of them — 🎉 for the arrival, ✅ for the thing that reassures.

**Everything else was already decided with them.** Which filter default ships,
the button that restores the notebook's value, which pages are hidden, what the
Documentation page holds — each was a question they answered while the app was
being built. Repeating it at the end is a changelog of a conversation they were
in, and this is the turn most likely to be read by someone who was not.

An ending can be six paragraphs of true facts and still be unreadable, because
true and already-agreed are not the same thing.

What earns a place at the end:

- **that it works**, in their terms — their own numbers, reproduced;
- **how to start it again**, the one thing they cannot work out for themselves;
- **at most one offer**, if there is a real next step.

A number belongs here only if it is theirs. "233 tests pass" is the framework
reassuring itself; "the same four peptides" is the user's own result handed back.

**The cleanup line does not belong here.** *"I also hid the template's example
pages and rewrote Documentation — the originals are still in `content/`"* is the
right sentence in the wrong turn: `cleanup.md` gives it to you to say **while
you are doing that work**, and a run that saves it for the sign-off ends on
housekeeping instead of on their result. Having already said it is what makes
the ending short.

If something genuinely new turned up — something you found that they have not
already seen — say that, in one sentence. **"They haven't seen it yet" does not
qualify work you simply never mentioned.** A run that skipped the cleanup line
reached the ending, noticed the user did not know about the hidden pages, and
opened with *"One thing you haven't seen yet:"* — the escape hatch is this
clause, and the fix for a missed line is not to append it here. New means new to
*you*: something the run turned up that neither of you could have known at the
start. Anything they chose, they already know.
And if they want the detail, they will ask; answering then costs one turn, while
volunteering it costs the ending.

### If you commit, check that the app is in the commit

Nothing here asks you to commit. If the user asks for one, or you offer and they
accept, then **verify what went in** — `git status` clean is not the same as the
app being committed, because a file that is ignored never shows as uncommitted.

The specific way this bites: a bare `python*` in `.gitignore`. Git matches that against **every path segment**, so
`src/python-tools/` was ignored, and `git add -A` silently refused the analysis
script — the one file the whole port exists to produce. The app's own tests
passed, the working tree looked clean, and a fresh clone would have installed an
app whose Configure page throws, because `input_python()` could not find its
tool.

The existing tools escaped only because they were committed before the rule
mattered; `.gitignore` does not apply to files already tracked. So this is
invisible in the template and appears the first time a generated app adds a file.

After committing:

```
git ls-files src/python-tools/ src/dashboards/ content/
```

Every file the port created should be listed. If one is missing, find the ignore
rule (`git check-ignore -v <path>`) and say so rather than working around it —
an ignore rule that swallows a generated file is a template defect, and
`scaffold-workflow-app` has what to do with those.

**Report the commit the way you report everything else: in their terms.** A
commit confirmation is still an ending, so the rule above still applies — *a
number belongs here only if it is theirs.* *"Working tree clean, 229 tests passing"* is a count of the framework's own
tests in the one sentence the user was going to read. `git status` and a test total are how **you** know it worked.
What they need is the branch, and what is on it.
