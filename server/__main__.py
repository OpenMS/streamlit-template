"""
Run the local web app: ``python -m server`` from the repository root.

Binds to 127.0.0.1 only, so nothing is reachable from other machines, and
opens the app in the default browser.
"""

import argparse
import threading
import webbrowser


def main() -> None:
    parser = argparse.ArgumentParser(description="OpenMS WebApp, Svelte frontend with a local server")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1", help="Keep the default to stay local-only.")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--reload", action="store_true", help="Restart on code changes (development).")
    args = parser.parse_args()

    import uvicorn

    url = f"http://{args.host}:{args.port}/"
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"OpenMS WebApp running at {url}")
    uvicorn.run("server.app:app", host=args.host, port=args.port, reload=args.reload, log_level="warning")


if __name__ == "__main__":
    main()
