"""HTTP API and the static Ask page."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fleetline.catalog import get_catalog
from fleetline.constants import AS_OF
from fleetline.models import AskRequest, AskResponse, BlankQuestion
from fleetline.service import ask, get_state

app = FastAPI(title="Fleetline", version="1.0.0")
STATIC = Path(__file__).resolve().parent / "static"


@app.get("/api/health")
def health() -> dict:
    state = get_state()
    return {
        "status": "ok",
        "as_of": AS_OF.isoformat(),
        "semantic_version": state.catalog.version,
        "rows": state.store.counts(),
    }


@app.get("/api/catalog")
def catalog() -> dict:
    loaded = get_catalog()
    return {
        "version": loaded.version,
        "as_of": AS_OF.isoformat(),
        "metrics": [
            {
                "key": metric.key,
                "label": metric.label,
                "description": metric.description,
                "format": metric.format,
                "fact": metric.fact,
                "synonyms": list(metric.synonyms),
            }
            for metric in loaded.metrics.values()
        ],
        "dimensions": [
            {
                "key": dimension.key,
                "label": dimension.label,
                "description": dimension.description,
                "facts": list(dimension.facts),
                "values": dimension.display_values(),
            }
            for dimension in loaded.dimensions.values()
        ],
        "examples": [{"area": example.area, "question": example.question} for example in loaded.examples],
    }


@app.post("/api/ask", response_model=AskResponse)
def ask_route(body: AskRequest) -> AskResponse:
    try:
        return ask(body.question, body.session_id)
    except BlankQuestion as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
