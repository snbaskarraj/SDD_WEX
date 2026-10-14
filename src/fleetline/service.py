"""Sessions, execution, and the chart metadata the page renders."""

from __future__ import annotations

import threading
import uuid
from datetime import date, datetime
from typing import Any

from fleetline.catalog import get_catalog
from fleetline.compiler import CompileError, compile_spec
from fleetline.models import AskResponse, BlankQuestion, Chart, Highlight, QuerySpec
from fleetline.narrate import format_value, leader_row, narrate
from fleetline.nlu import resolve
from fleetline.store import Store, open_store

_STATE_LOCK = threading.Lock()
_STATE: AppState | None = None


class AppState:
    def __init__(self, store: Store) -> None:
        self.store = store
        self.catalog = get_catalog()
        self.sessions: dict[str, QuerySpec] = {}
        self.lock = threading.Lock()


def get_state() -> AppState:
    global _STATE
    with _STATE_LOCK:
        if _STATE is None:
            _STATE = AppState(open_store())
        return _STATE


def reset_state() -> None:
    global _STATE
    with _STATE_LOCK:
        _STATE = None


def _param(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return value
    return value


def _highlight(spec: QuerySpec, rows: list[dict], catalog) -> Highlight | None:
    metric = catalog.metric(spec.metric)
    if not spec.group_by:
        value = rows[0]["value"] if rows else None
        if not isinstance(value, (int, float)):
            value = None
        return Highlight(kind="total", label=metric.label, value=value, format=metric.format)
    leader = leader_row(spec, rows)
    if leader is None:
        return None
    label = " · ".join(str(leader[key]) for key in spec.group_by)
    kind = "peak" if spec.order_by == "month" else "leader"
    return Highlight(kind=kind, label=label, value=float(leader["value"]), format=metric.format)


def ask(question: str, session_id: str | None = None) -> AskResponse:
    if question is None or not str(question).strip():
        raise BlankQuestion("Question is required.")
    if len(question) > 500:
        raise BlankQuestion("Question is too long.")
    state = get_state()
    catalog = state.catalog
    sid = (session_id or "").strip() or uuid.uuid4().hex
    with state.lock:
        previous = state.sessions.get(sid)
        previous = previous.model_copy(deep=True) if previous else None
    resolved = resolve(question, previous, catalog)
    suggestions = resolved.suggestions
    if resolved.status != "answer" or resolved.spec is None:
        return AskResponse(
            status="clarify",
            message=resolved.message,
            session_id=sid,
            suggestions=suggestions,
        )
    spec = resolved.spec
    try:
        sql, params = compile_spec(spec, catalog)
        rows = state.store.query(sql, params)
    except CompileError as exc:
        return AskResponse(status="clarify", message=str(exc), session_id=sid, suggestions=suggestions)
    message = narrate(spec, rows, catalog)
    chart = None
    if spec.group_by and rows:
        chart = Chart(type="line" if "month" in spec.group_by else "bar", format=catalog.metric(spec.metric).format)
    columns = list(rows[0]) if rows else [*spec.group_by, "value"]
    with state.lock:
        if len(state.sessions) > 200:
            state.sessions.pop(next(iter(state.sessions)))
        state.sessions[sid] = spec.model_copy(deep=True)
    return AskResponse(
        status="answer",
        message=message,
        session_id=sid,
        spec=spec,
        sql=sql,
        params=[_param(value) for value in params],
        columns=columns,
        rows=rows,
        chart=chart,
        highlight=_highlight(spec, rows, catalog),
    )
