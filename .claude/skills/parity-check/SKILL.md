---
name: parity-check
description: Use when comparing an OpenMS web app against a reference tool or an older app version (feature parity, result parity), or when updating a parity progress file.
---

# Parity check

Compare an app with a reference (another tool such as a desktop viewer or a
published pipeline, or the app's own previous version) on two axes, and keep
the outcome in one progress file the next run continues from.

## Two kinds of parity

- **Feature parity**: can a user do in the app what they can do in the
  reference? Unit: a user task ("filter PSMs by q-value", "see the fragment
  ion table for a spectrum").
- **Result parity**: on the same input and comparable parameters, do the
  numbers agree? Unit: a count or a value with a tolerance (identified
  proteoforms at 1% FDR, feature m/z within 5 ppm).

## Steps

1. **Fix the reference**: tool and version, input files, parameters. Without
   these a parity claim cannot be repeated.
2. **List features** of the reference from its documentation and UI, as user
   tasks. Group by page or view.
3. **Check each** in the app: present / partial / missing, with the page and a
   screenshot path for present and partial.
4. **Run both on the same input** for result parity. Record each compared
   quantity, both values, the tolerance, pass/fail. Explain each fail
   (parameter difference, different algorithm, bug) before calling it a gap.
5. **Write the progress file** (`feature-gaps/<app>-vs-<reference>.md` or the
   app's own docs folder):

   ```markdown
   # <App> vs <Reference> <version>
   Input: <files>  Parameters: <link or table>  Checked: <date>

   | Task | Status | Where / gap | Issue/PR |
   |---|---|---|---|
   ```

   plus a result-parity table. Update rows in place on the next run; do not
   start a new file.
6. **Turn gaps into work**: one issue or PR per missing task, linked from its
   row. A gap in template-owned code goes through `upstream-to-template`.

## Checklist

- [ ] Reference version, input and parameters recorded
- [ ] Every reference task has a status
- [ ] Result differences explained before being called gaps
- [ ] Progress file updated in place, gaps linked to issues/PRs
