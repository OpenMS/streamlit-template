---
name: verify-webapp-usability
description: Use when checking that a Streamlit results page actually renders and is usable, when OpenMS-Insight panels need verifying in a real browser, or when a page passes its tests but nobody has looked at it.
---

# Verify webapp usability

Gate a results page in a real browser: hard assertions for correctness, a
screenshot for judgement.

**This whole stage is internal.** The gate, the screenshot, the component count,
`--ignore-console` — none of it appears in a user-facing turn. What a failure
becomes is a fix, made before the page is shown; what a design note becomes is a
suggestion in the user's own words, in the round that follows. A user told *"the
gate passed 11/11 and I've opened the screenshot"* has been given the framework's
homework instead of their app.

## The rule

**A results page built from OpenMS-Insight components cannot be verified with
`AppTest`.**

`streamlit.testing.v1.AppTest` executes no JavaScript. Insight components are
custom bidirectional Vue components in iframes, so a page whose every panel
fails to render still passes every AppTest assertion. Keep AppTest for what it
can see — page boot, Streamlit-native widgets, parameter round-tripping — and
gate the dashboard here.

**And keep the Results page out of `test_launch` entirely.** It does not merely
fail to *see* the panels — measured on three generated apps, constructing an
Insight component under AppTest raises `RuntimeError: Preprocessing failed with
exit code 1`, so the page cannot be launched at all there. The other pages of a
generated app launch clean and belong in that list; this one is covered here, and
listing it buys a failing test rather than coverage.

## Running it

```bash
python gate.py --url http://localhost:8501/ --nav "Results" \
    --expect-components 2 --screenshot results.png
```

Use `--nav` rather than a direct page URL. Opening a sub-page URL directly makes
Streamlit resolve `/_stcore/health` and `/_stcore/host-config` relative to that
path, producing two 404s that are an artefact of the test, not a defect. Clicking
the sidebar link is also what a user does.

## What it asserts

- page boots with no Python traceback and no `stException` block
- no uncaught JS page errors; browser console clean
- every declared panel renders **with real width and height** — a zero-height
  iframe is the failure mode to catch, because the component mounts and reports
  no error. `--expect-components` is the **total** panel count: Insight iframes
  plus fallback panels drawn with pyopenms-viz through `show_fig()`, which are
  native Streamlit charts, not iframes. Counting iframes alone marks a dashboard
  down for following the fallback rule in `build-insight-dashboard`
- **no panel is stuck loading.** A panel filtering on a link identifier that
  nothing sets and no `filter_defaults` value covers shows "Loading…" forever
  while passing every other check: the iframe has real size, the console is
  clean, nothing throws. The gate reads inside each iframe after settling and
  fails on a panel whose entire content is a placeholder
- the page is not blank; no horizontal scrollbar
- clicking a row in the master panel changes a linked panel
- first paint within budget

Then it saves a screenshot. **Look at it.** The assertions cannot see that a
column header is truncated, or that one half of a mirror plot is flattened onto
the baseline by a shared axis. Both of those passed every check on a real build
and were caught only by looking.

## The second job: design input

The gate runs twice for different reasons. During `build-insight-dashboard` it
runs *before* the final whole-page design round, and its output feeds that round's
suggestions — so it also prints **design notes**: panels below the fold, a missing
summary strip, a column header with no slack left. These are observations, not failures, and
they are written to be read by the user rather than by a log.

When you relay them, keep them in the user's language. "Nothing is selected when
the page opens, so the 3D panel is empty on arrival" — not `warn: no default
selection`. A finding the user cannot picture is a finding they will skip.

## Waiting correctly

Never sample after a fixed sleep. Streamlit streams output while the script is
still running, and Insight preprocesses large tables in a subprocess before its
component mounts — so a fixed wait screenshots a half-rendered page and reports
missing panels that are merely late. The gate polls Streamlit's own
`stStatusWidget` until it clears, then waits either for the expected panels to
appear or for the iframe count to stop changing — whichever comes first.

**A screenshot that times out is a page mid-rerun — re-navigate, don't retry.**
Driving the app yourself, every click reruns the script, and a screenshot taken
during that rerun comes back *"Script injection timed out … the page is busy or
mid-navigation"*. Retrying the screenshot fails again for the same reason; one
run lost three calls to that twice over. Navigating to the page's URL again
returns it in a settled state, and the screenshot then works.

**Never wait on a count that mixes iframes with native panels.** `settle()` also
exits once the app is idle and the iframe count has stopped changing, because
`--expect-components` is the *total* — a page with two Insight iframes plus one
`show_fig()` panel would otherwise wait for a third iframe that never arrives and
burn the full timeout. That bug ran for twenty gate invocations reporting 96.5s
first paint on the one app with a fallback panel, and was read as a slow page.

`full_page=True` does not work here: Streamlit scrolls its main container, not
the document, so a full-page shot captures only the first viewport. The gate
grows the viewport instead (`--capture-height`).

## Ignoring benign errors

`--ignore-console` takes a substring, and applies to console errors, page errors
and failed requests. Use it only for a known upstream error, and record why. For
this template, Tabulator emits `Scroll Error - Row not visible` when it scrolls
to a default row before layout completes; it is harmless and not fixable from
the app.

Every other error is the app's problem. An ignore entry with no justification is
how a gate stops catching anything.

## Common mistakes

- Trusting a green gate as proof the page is good. Green means it works;
  the screenshot is where quality is judged.
- **Trusting a green gate as proof the app produced what it is showing.** The
  gate opens a results page and reads what is on it. It cannot tell an output
  `execution()` wrote from one dropped into the results directory by hand, and
  both render identically. Measured: all three corpus apps passed this gate at
  1.000 for **ninety ticks** while their workspaces held nothing but seeded
  files — no `params.json`, no `logs/`, and a `seed.json` naming the tool
  invocation that had produced them. `execution()` had never run once.
  A workspace with `results/` and no `logs/` beside it was filled by hand; the
  smoke run in `scaffold-workflow-app` is what stops this.
- Not restarting the server after editing a `src/` module. The gate will
  keep reporting an exception you have already fixed, because Streamlit did not
  re-import the module.
- Leaving a stale Insight cache after changing a component config, then
  concluding the change did nothing.
