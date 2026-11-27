"""Start ``streamlit run`` after importing the app's heavy libraries.

The container (``docker/entrypoint.sh``, ``k8s/base``) and the desktop app
start Streamlit with ``python -m src.streamlit_launcher run app.py ...``
instead of ``streamlit run app.py ...``.

Preloading. Streamlit runs every page in the server process, so a library a
page imports stays imported for every later session. Without a preload the
first visitor after a restart waits for it: the daily first-load check measured
pandas at 4 to 10 s and pyopenms at 4 to 12 s on a cold disk, most of it reading
the files. The launcher imports them before the server starts, so a pod
becomes ready a few seconds later and the first page is drawn without that
wait. What is preloaded is the list ``"preload": ["module", ...]`` in
``settings.json``, nothing else; the template lists pandas and pyopenms, and an
app lists its own. A module that is not installed, or fails to import, is
skipped: the page that needs it imports it as before.

polars first, on the main thread. Streamlit runs ``app.py`` in a script thread
that ends after each rerun, so the first ``import polars`` of a plain
``streamlit run`` happens on a thread that later exits. On Windows, polars'
bundled allocator (mimalloc before 3.4.1) can then read the exited thread's
allocator state, and a later polars call on another thread dies with an access
violation (polars issues #29883 and #30362). Importing polars here, on the main
thread, which lives as long as the server, avoids that, so an app that uses
polars lists it in ``"preload"`` (a test checks this against requirements.txt)
and the launcher imports it before the other modules. Every module is imported
on the main thread for the same reason.
"""

from __future__ import annotations

import importlib
import json
import sys
import time
from pathlib import Path

# Imported before every other preloaded module (see the module docstring).
FIRST = ("polars",)


def settings_preload(path: Path | str = "settings.json") -> list:
    """The modules ``settings.json`` adds to the preload (``"preload"``)."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8")).get("preload", [])
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(value, list):
        return []
    return [m for m in value if isinstance(m, str) and m.strip()]


def preload_modules(path: Path | str = "settings.json") -> tuple:
    """The modules of ``settings.json``'s ``"preload"``, each once, polars first."""
    modules = list(dict.fromkeys(settings_preload(path)))
    return tuple(sorted(modules, key=lambda m: m not in FIRST))


def preload(modules=None, log=None) -> list:
    """Import ``modules`` and return the names that imported.

    A module that is not installed, or raises while importing, is skipped and
    named in the log, so the server starts as it would without it.
    """
    if modules is None:
        modules = preload_modules()
    log = log or (lambda msg: print(msg, file=sys.stderr, flush=True))
    loaded = []
    for name in modules:
        start = time.perf_counter()
        try:
            importlib.import_module(name)
        except ImportError:
            continue
        except Exception as e:  # pylint: disable=broad-except
            log(f"preload: {name} failed to import, skipped ({type(e).__name__}: {e})")
            continue
        loaded.append(name)
        log(f"preload: {name} in {time.perf_counter() - start:.1f} s")
    return loaded


def main(argv=None) -> int:
    preload()
    from streamlit.web import cli

    sys.argv = ["streamlit", *(sys.argv[1:] if argv is None else argv)]
    return cli.main()


if __name__ == "__main__":
    sys.exit(main())
