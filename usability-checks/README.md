# Usability checks for the OpenMS web apps

A daily Playwright sweep of every app built on this template: streamlit-template,
quantms-web (OpenDDA), OpenDIAKiosk, FLASHApp and umetaflow.

```bash
usability-checks/run.sh [OUT_DIR] [APP ...]   # all apps in apps.json by default
```

For each app `run.sh` shallow-clones the default branch, installs
`requirements.txt` into a cached venv (`$VENV_DIR`, default `/tmp/venvs`),
starts Streamlit and runs `check.mjs`, which:

- opens every page in the sidebar navigation twice: in a fresh workspace and in
  a copy of the app's demo workspace (`example-data/workspaces/<demo>`);
- fails a page on a rendered Python exception, an uncaught browser error, a
  Streamlit "Page not found", or a script run that does not finish within
  `PAGE_TIMEOUT_MS` (default 120 s);
- warns on `st.error` boxes and browser console errors;
- screenshots every page;
- for apps with `exampleWorkflow`, loads the example mzML files and runs the
  pyOpenMS example workflow end to end.

Apps with a `live` URL are also opened at their deployment. Those run in online
mode behind the captcha, so the live check covers the landing page only.

The check environment has pyOpenMS but no TOPP binaries, so pages that need a
TOPP tool report it as a note, not a failure.

Output: `OUT_DIR/report.md` (summary), `OUT_DIR/<app>/results.json`,
`OUT_DIR/<app>/screenshots/*.png`, `streamlit.log`, `setup.log`.
Needs Node with Playwright (`npm i -g playwright`), `uv`, `git` and Python 3.11.
