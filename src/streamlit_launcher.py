"""Start ``streamlit run`` after importing polars on the main thread.

The desktop app starts Streamlit with ``python -m src.streamlit_launcher run
app.py ...`` instead of ``python -m streamlit run app.py ...``.

Streamlit runs ``app.py`` in a script thread that ends after each rerun, so the
first ``import polars`` of a plain ``streamlit run`` happens on a thread that
later exits. On Windows, polars' bundled allocator (mimalloc before 3.4.1) can
then read the exited thread's allocator state, and a later polars call on
another thread dies with an access violation (polars issues #29883 and
#30362). Importing polars here, on the main thread, which lives as long as the
server, avoids that.
"""

from __future__ import annotations

import importlib
import sys

# Modules imported on the main thread before Streamlit starts.
PRELOAD = ("polars",)


def preload(modules=PRELOAD) -> list:
    """Import ``modules`` and return the names that imported.

    A module that is not installed is skipped, so an app without polars starts
    as before.
    """
    loaded = []
    for name in modules:
        try:
            importlib.import_module(name)
        except ImportError:
            continue
        loaded.append(name)
    return loaded


def main(argv=None) -> int:
    preload()
    from streamlit.web import cli

    sys.argv = ["streamlit", *(sys.argv[1:] if argv is None else argv)]
    return cli.main()


if __name__ == "__main__":
    sys.exit(main())
