#!/usr/bin/env python3
"""Serves the built app (dist/) on this computer: python3 serve.py [port] [--no-browser]

The app runs entirely in the browser (OpenMS as WebAssembly); this only hands
the browser its files, from localhost, with the cross-origin isolation headers
OpenMS's threads need and the MIME types older Pythons lack. Any static server
works too: the app then adds the headers with a service worker (public/coi-sw.js).
"""

import functools
import http.server
import os
import sys
import webbrowser

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {
        **http.server.SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".wasm": "application/wasm",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".mzML": "application/xml",
    }

    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        # revalidate, but keep: the browser caches the compiled WebAssembly module
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *args):
        pass


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    port = int(args[0]) if args else 8501
    if not os.path.isfile(os.path.join(ROOT, "index.html")):
        sys.exit("No build found: run `npm install && npm run build` in frontend/ first.")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, directory=ROOT))
    url = f"http://localhost:{port}/"
    print(f"OpenMS WebApp: {url}  (Ctrl+C stops)")
    if "--no-browser" not in sys.argv:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
