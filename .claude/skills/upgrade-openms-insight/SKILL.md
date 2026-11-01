---
name: upgrade-openms-insight
description: Use when bumping openms-insight (the Vue-based Table, LinePlot, Heatmap, VolcanoPlot, SequenceView components) in one or more apps, or when an Insight upgrade broke a view.
---

# Upgrade openms-insight

openms-insight is not a template dependency; each app pins it in its own
`requirements.txt` (for example `openms-insight==0.3.1`). An upgrade therefore
runs per app, in one PR per app, with the same steps.

## Steps

1. **Read the changelog** between the pinned and the target version (GitHub
   releases of `t0mdavid-m/openms-insight`, or the PyPI history). Note renamed
   arguments, changed defaults, and changes to selection/cross-linking
   identifiers: those break silently, a view still renders but stops
   filtering the others.
2. **Find every use** in the app:
   ```bash
   grep -rn "openms_insight\|from openms_insight\|show_insight_table" --include='*.py' .
   ```
3. **Bump the pin** (exact `==` pin, not `>=`: an unpinned Insight upgrade has
   changed views under a running deployment before) and install it.
4. **Adapt call sites** to renamed or removed arguments.
5. **Prove it renders and links.** AppTest cannot see Insight components, so
   tests passing proves nothing about the views. Start the app, open every
   results page that uses Insight with the demo workspace or example data, and
   check per view: it renders, pagination/zoom works, and selecting in one
   component updates the linked ones. `verify-webapp-usability` (`gate.py`)
   automates the render check. Compare against screenshots from the old
   version where the layout matters.
6. **Theme**: check both light and dark theme; Insight reads the theme from
   Streamlit's render args.
7. **PR** per app, listing the views checked.

## Several apps at once

Do the app with the most Insight views first (quantms-web), fix what breaks,
then the others. A fix needed in more than one app that belongs in a shared
helper (`src/common/insight_tables.py` style) goes through
`upstream-to-template` if the helper is template-owned.

## Checklist

- [ ] Changelog read; breaking changes listed
- [ ] Exact pin bumped
- [ ] Every Insight results page opened and cross-linking checked, light and dark
- [ ] One PR per app with the views checked
