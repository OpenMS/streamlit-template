#!/usr/bin/env python3
"""
Reference share service for the in-browser app's "Share workspace" button.

The app runs entirely in the browser; a workspace leaves it only when its user
clicks Share. The app then uploads the workspace as a ZIP here and gets an id;
the link ?shared=<id> makes another browser download it and open it as a new
workspace. Point "share_url" in settings.json (or VITE_SHARE_URL at build
time) at where this runs.

    python3 share.py [--port 8502] [--dir shares] [--max-mb 500] [--days 30] [--origin '*']

POST /shares        body: the ZIP           -> 201 {"id": "<id>"}
GET  /shares/<id>                           -> the ZIP, or 404

Shares are deleted after --days. Standard library only; put it behind a
reverse proxy with TLS for anything beyond a local network.
"""

import argparse
import http.server
import json
import os
import re
import secrets
import time
import zipfile

ID = re.compile(r"^/shares/([A-Za-z0-9_-]{6,64})$")


def make_handler(cfg):
    class Handler(http.server.BaseHTTPRequestHandler):
        def cors(self):
            self.send_header("Access-Control-Allow-Origin", cfg.origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            # the app's page is cross-origin isolated (COEP require-corp)
            self.send_header("Cross-Origin-Resource-Policy", "cross-origin")

        def reply(self, code, body=b"", ctype="application/json"):
            self.send_response(code)
            self.cors()
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def error(self, code, message):
            self.reply(code, json.dumps({"error": message}).encode())

        def do_OPTIONS(self):
            self.send_response(204)
            self.cors()
            self.end_headers()

        def do_POST(self):
            if self.path.rstrip("/") != "/shares":
                return self.error(404, "not found")
            size = int(self.headers.get("Content-Length") or 0)
            if size <= 0:
                return self.error(411, "the upload needs a Content-Length")
            if size > cfg.max_mb * 1024 * 1024:
                return self.error(413, f"larger than {cfg.max_mb} MB")
            sid = secrets.token_urlsafe(12)
            path = os.path.join(cfg.dir, f"{sid}.zip")
            with open(path, "wb") as f:
                left = size
                while left:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            if left or not zipfile.is_zipfile(path):
                os.remove(path)
                return self.error(400, "not a ZIP file")
            expire(cfg)
            self.reply(201, json.dumps({"id": sid}).encode())

        def do_GET(self):
            m = ID.match(self.path)
            path = m and os.path.join(cfg.dir, f"{m.group(1)}.zip")
            if not path or not os.path.isfile(path):
                return self.error(404, "no such share")
            with open(path, "rb") as f:
                self.reply(200, f.read(), "application/zip")

    return Handler


def expire(cfg):
    limit = time.time() - cfg.days * 86400
    for name in os.listdir(cfg.dir):
        p = os.path.join(cfg.dir, name)
        if name.endswith(".zip") and os.path.getmtime(p) < limit:
            os.remove(p)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8502)
    ap.add_argument("--dir", default="shares")
    ap.add_argument("--max-mb", type=int, default=500)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--origin", default="*", help="the app's origin allowed to upload and download (CORS)")
    cfg = ap.parse_args()
    os.makedirs(cfg.dir, exist_ok=True)
    expire(cfg)
    server = http.server.ThreadingHTTPServer((cfg.host, cfg.port), make_handler(cfg))
    print(f"Share service on http://{cfg.host}:{cfg.port}/shares, storing in {os.path.abspath(cfg.dir)}")
    server.serve_forever()


if __name__ == "__main__":
    main()
