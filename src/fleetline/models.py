"""Request and answer shapes. AskRequest rejects unknown fields."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Filter(BaseModel):
    dimension: str
    values: list[str]


class TimeRange(BaseModel):
    start: date
    end: date
    label: str


class QuerySpec(BaseModel):
    metric: str
    group_by: list[str] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    time_range: TimeRange
    order: Literal["asc", "desc"] = "desc"
    order_by: Literal["value", "month"] = "value"
    limit: int | None = None


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = ""
    session_id: str | None = None


class Chart(BaseModel):
    type: Literal["bar", "line"]
    format: str


class Highlight(BaseModel):
    kind: Literal["total", "leader", "peak"]
    label: str
    value: float | None
    format: str


class AskResponse(BaseModel):
    status: Literal["answer", "clarify"]
    message: str
    session_id: str
    suggestions: list[str] = Field(default_factory=list)
    spec: QuerySpec | None = None
    sql: str | None = None
    params: list[Any] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    chart: Chart | None = None
    highlight: Highlight | None = None


class BlankQuestion(ValueError):
    """The caller sent an empty question."""
