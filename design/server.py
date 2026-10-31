"""Local design canvas for Kayé documents.

Run:  uv run uvicorn design.server:app --reload --reload-dir app/documents --reload-dir design --port 8765
Open: http://localhost:8765

Previews are rendered from the real templates (app/documents/templates) with fictitious fixtures.
Edit a template or the registry and the open canvas refreshes its previews by itself.
"""

import hashlib
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.documents.fixtures import FIXTURES
from app.documents.render import TEMPLATES, render
from design import registry

ROOT = Path(__file__).resolve().parent.parent
CANVAS = Path(__file__).parent / "canvas"
WATCHED = [TEMPLATES, CANVAS, Path(__file__).parent, ROOT / "app" / "documents"]

app = FastAPI(title="Kayé design canvas", docs_url=None, redoc_url=None)
app.mount("/brand", StaticFiles(directory=ROOT / "assets" / "brand"), name="brand")
app.mount("/canvas", StaticFiles(directory=CANVAS), name="canvas")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(CANVAS / "index.html")


@app.get("/registry")
def get_registry() -> list[dict]:
    return registry.as_json()


@app.get("/preview/{item_id}", response_class=HTMLResponse)
def preview(item_id: str) -> str:
    item = registry.get(item_id)
    if item is None or item.fixture not in FIXTURES:
        raise HTTPException(404, "unknown canvas item")
    return render(item.template, FIXTURES[item.fixture]())


@app.get("/version")
def version() -> dict[str, str]:
    """Changes whenever a watched source file changes; the canvas polls it to refresh previews."""
    h = hashlib.sha1()
    for folder in WATCHED:
        for path in sorted(folder.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                h.update(f"{path}:{path.stat().st_mtime_ns}".encode())
    return {"v": h.hexdigest()[:12]}
