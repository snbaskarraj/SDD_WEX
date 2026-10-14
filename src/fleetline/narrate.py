"""Deterministic sentences. The figure always comes from the result rows."""

from __future__ import annotations

from fleetline.catalog import Catalog
from fleetline.constants import DEFAULT_TIME_LABEL
from fleetline.models import QuerySpec


def format_value(value: float | None, fmt: str) -> str:
    if value is None:
        return "n/a"
    if fmt == "currency":
        if abs(value) >= 100:
            return f"${value:,.0f}"
        return f"${value:,.2f}"
    if fmt == "unit_price":
        return f"${value:,.2f}"
    if fmt == "percent":
        return f"{value * 100:.1f}%"
    if fmt == "gallons":
        return f"{value:,.0f} gal"
    if fmt == "days":
        return f"{value:,.1f} days"
    if fmt == "count":
        return f"{value:,.0f}"
    return f"{value:,.2f}"


def _head(spec: QuerySpec, catalog: Catalog) -> str:
    metric = catalog.metric(spec.metric)
    parts = [metric.label]
    if spec.group_by:
        labels = [catalog.dimension(key).label.lower() for key in spec.group_by]
        parts.append("by " + " and ".join(labels))
    qualifiers: list[str] = []
    if spec.filters:
        rendered = []
        for item in spec.filters:
            label = catalog.dimension(item.dimension).label.lower()
            values = " and ".join(item.values)
            rendered.append(f"{label} is {values}")
        qualifiers.append("where " + " and ".join(rendered))
    if spec.time_range.label == DEFAULT_TIME_LABEL:
        qualifiers.append("from Apr 2025 through Sep 2026")
    else:
        qualifiers.append(f"for {spec.time_range.label}")
    sentence = " ".join(parts)
    if qualifiers:
        sentence = sentence + ", " + ", ".join(qualifiers)
    return sentence


def _numeric(rows: list[dict]) -> list[dict]:
    return [row for row in rows if isinstance(row.get("value"), (int, float))]


def leader_row(spec: QuerySpec, rows: list[dict]) -> dict | None:
    valid = _numeric(rows)
    if not valid:
        return None
    if spec.order_by == "value":
        return valid[0]
    return max(valid, key=lambda row: row["value"])


def narrate(spec: QuerySpec, rows: list[dict], catalog: Catalog) -> str:
    head = _head(spec, catalog)
    fmt = catalog.metric(spec.metric).format
    valid = _numeric(rows)
    if not valid:
        return f"No data matched {head}."
    if not spec.group_by:
        return f"{head} was {format_value(valid[0]['value'], fmt)}."
    leader = leader_row(spec, valid)
    assert leader is not None
    name = " · ".join(str(leader[key]) for key in spec.group_by)
    amount = format_value(leader["value"], fmt)
    if spec.order_by == "month":
        return f"{head} peaked at {amount} in {name}."
    if spec.order == "asc":
        return f"{head} was lowest for {name} at {amount}."
    return f"{head} was highest for {name} at {amount}."
