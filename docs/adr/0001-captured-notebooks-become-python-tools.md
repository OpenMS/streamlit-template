# Captured notebooks become python tools, not simple pages

A source notebook's analysis is captured into `src/python-tools/<name>.py` and
driven by a `WorkflowManager` subclass, rather than into a simple page calling
`page_setup()`/`save_params()`. The workflow framework's `run_python()` invokes a
python tool as a subprocess with a JSON parameter file and no Streamlit import,
which makes the isolation we need structural rather than conventional: the
processing step is testable with plain pytest, unreachable from `st.session_state`,
and its `DEFAULTS` list generates the configuration page for free.

## Considered Options

Simple pages are much lighter and would produce less code, but isolation would be
a convention a generator could quietly break, parameters would land in one flat
global namespace shared with every other page, and there would be no run button,
log, cancellation or online queue. Choosing per notebook was rejected because a
general-purpose framework with two shapes has two test strategies and two tutorials.

## Consequences

Every generated app inherits the workflow slug's three-way coupling (directory,
`presets.json` key, session-state prefixes), so renaming a captured workflow
orphans its parameters. Apps that use no TOPP tools still carry the framework, but
they build with `Dockerfile_simple` and never generate an `.ini`.
