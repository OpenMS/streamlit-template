"""FastAPI application: the API under /api and the built Svelte app under /."""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .core import ROOT, ensure_cwd

ensure_cwd()

from .routes import msdata, toolbox, workflow, workspaces  # noqa: E402


def _quiet_streamlit() -> None:
    # The reused src/workflow modules import Streamlit; outside `streamlit run`
    # every session-state access logs a "missing ScriptRunContext" warning.
    for name in list(logging.root.manager.loggerDict):
        if name.startswith("streamlit"):
            logging.getLogger(name).setLevel(logging.ERROR)


_quiet_streamlit()

DIST = ROOT / "frontend" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(title="OpenMS WebApp (local)", docs_url="/api/docs-ui", openapi_url="/api/openapi.json")
    for r in (workspaces.router, workflow.router, toolbox.router, msdata.router):
        app.include_router(r, prefix="/api")

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    @app.get("/assets/openms-logo.svg")
    def logo() -> FileResponse:
        return FileResponse(ROOT / "assets" / "openms_transparent_bg_logo.svg")

    # Single-page app: any non-API path serves a built file or index.html
    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        if not DIST.exists():
            raise HTTPException(
                503,
                "The frontend is not built. Run `npm install && npm run build` in frontend/, "
                "or `npm run dev` there for development.",
            )
        target = (DIST / path).resolve()
        if path and target.is_file() and DIST.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(DIST / "index.html")

    return app


app = create_app()
