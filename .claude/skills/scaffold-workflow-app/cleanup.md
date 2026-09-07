# Clearing the template's pages, and rewriting Documentation

Part of `scaffold-workflow-app`. Read this when you are about to edit `app.py` or `content/documentation.py`.

The template ships **16 pages in five sections** (`grep -c st.Page app.py`); the
captured workflow adds four, so the user's app would be 4 pages of 20 and theirs
would not be the first in the sidebar. Hide **every** template section by
commenting it out of the `pages` dict in `app.py`:

| section | pages | |
|---|---|---|
| `TOPP Workflow Framework` | 4 | the template's example workflow |
| `pyOpenMS Workflow` | 4 | a second example workflow |
| `pyOpenMS Toolbox` | 4 | digest, m/z, isotope pattern, fragment ions |
| `Others Topics` | 2 | `Simple Workflow`, `Run Subprocess` |
| `Quickstart` | 1 | the page that generates an app — they just did |

Five rows, fifteen pages — not five *sections*. `Quickstart` is one page inside
the app-name section it shares with `Documentation`, so hiding it removes a row
rather than a whole section, and that section is the sixth. Fifteen hidden leaves
`Documentation` plus the workflow's four: **five live pages** of the sixteen the
template shipped. The `pyOpenMS Toolbox` utilities go too. They are working tools, which
is exactly why keeping them is tempting — but the user asked for their notebook
as an app, not for their notebook plus four calculators, and every row in that
sidebar is a row they have to rule out before they find their own.

**`Documentation` stays, and its body is replaced.** Shipped as-is it is the
*template's developer guide* — "How to build app based on this template", "TOPP
Workflow Framework", "Kubernetes Deployment" — so a scientist who clicks
Documentation in their own app gets instructions for building Streamlit
templates. Rewrite `content/documentation.py` from the notebook's **markdown
cells**: the author already explained what the analysis does, in their own words,
next to the code that does it. That is the documentation this app should ship
with, and it costs nothing to write because it is already written.

Two things make this less mechanical than it sounds:

- **A markdown cell is not a chapter.** Cells with no heading continue the
  previous section, and one cell often carries several `#` headings. Split the
  concatenated markdown at its headings, not at cell boundaries — splitting per
  cell produced 23 "chapters" from a notebook with 8 real sections, most titled
  `Section 11`.
- **Not all of it is documentation.** A teaching notebook carries explanation
  (keep), environment scaffolding — *"Install dependencies (for Google Colab)"* —
  and troubleshooting appendices — *"Error: ModuleNotFoundError"*, *"Output:
  scores = [0, 0, 0]"*. The last two exist because the notebook must run on a
  stranger's machine during a workshop. The app has neither problem: it ships its
  environment and nobody runs its cells. Carrying them over swaps one kind of
  irrelevant documentation for another.

**Update `test_gui.py` in the same edit — all three of its hand-written lists.**

1. **The launch list** (`test_gui.py:22-36`) names every page it opens. Add your
   four (Results excepted — see `verify-webapp-usability`) **and remove the ones
   you just hid**. Two halves, and doing one is not doing it: add the new pages while leaving the hidden ones and the suite passes while launching pages the sidebar no longer offers.
2. **The page-specific tests below it**, which are easy to miss because the
   launch list looks like the whole job. `test_file_upload_load_example`,
   `test_view_raw_ms_data` and `test_run_workflow` each name a page you have
   just hidden. Comment them out with their decorators — same reason the pages
   are commented rather than deleted: un-hiding a page should bring its test
   back with it.

   A list of two is not a list of one with an obvious extension: an enumerated
   list is read as the scope.
3. **The chapter list** (`test_gui.py:50-61`) names the eight documentation
   chapters by hand, so replacing the chapters without replacing that list fails
   eight tests whose message says nothing about documentation.

The same trap three times, and one cause: the file lists what it tests instead
of discovering it. No list updates itself and no failure names its reason.

**Comment out; do not delete.** One line brings a page back, and `test_gui.py`
lists every page **by hand** (`test_gui.py:22-36`) instead of globbing `content/`
— delete a file without editing that list and CI fails at collection, before a
single test runs. Hiding needs no test change at all.

Because it is reversible it is not a question. One line, **said here, while you
are doing it**: *"Hid the template's own 15 example pages, and rewrote
Documentation from your notebook's notes — the originals are still in `content/`
if you want any back."*

**Not saved for the sign-off.** A line that explains what you are doing is worth saying while you do it
and worth nothing afterwards, because by then it explains something already
done. `handover.md` has what the ending is for.

