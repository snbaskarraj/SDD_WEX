"""Turn a QuerySpec into one SELECT.

Identifiers come from the catalog. Filter values are bound parameters.
Nothing else in the process writes SQL.
"""

from __future__ import annotations

import re

from fleetline.catalog import Catalog
from fleetline.models import QuerySpec

_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")

_FROM = {
    "transactions": """
FROM transactions t
JOIN customers c ON t.customer_id = c.customer_id
JOIN cards cd ON t.card_id = cd.card_id
JOIN merchants m ON t.merchant_id = m.merchant_id
""".strip(),
    "invoices": """
FROM invoices i
JOIN customers c ON i.customer_id = c.customer_id
""".strip(),
}
_TIME_COL = {
    "transactions": "t.txn_date",
    "invoices": "i.invoice_month",
}


class CompileError(ValueError):
    """The spec cannot be compiled. This is a bug if the interpreter produced it."""


def compile_spec(spec: QuerySpec, catalog: Catalog) -> tuple[str, list[object]]:
    if spec.metric not in catalog.metrics:
        raise CompileError(f"Unknown metric {spec.metric}.")
    metric = catalog.metric(spec.metric)
    fact = metric.fact
    if not spec.time_range:
        raise CompileError("A time range is required.")
    if len(spec.group_by) > 2:
        raise CompileError("At most two breakdowns are supported.")
    if spec.limit is not None and (
        isinstance(spec.limit, bool) or not isinstance(spec.limit, int) or not 1 <= spec.limit <= 100
    ):
        raise CompileError("Limit is out of range.")
    if spec.order_by == "month" and "month" not in spec.group_by:
        raise CompileError("Chronological order requires a month breakdown.")

    select_parts: list[str] = []
    for key in spec.group_by:
        if not _IDENT.match(key) or key not in catalog.dimensions:
            raise CompileError(f"Unknown breakdown {key}.")
        if not catalog.allows(key, fact):
            raise CompileError(f"{catalog.dimension(key).label} does not apply to {metric.label}.")
        select_parts.append(f"{catalog.select_expr(key, fact)} AS {key}")
    select_parts.append(f'CAST({metric.expression} AS DOUBLE) AS "value"')

    params: list[object] = [spec.time_range.start, spec.time_range.end]
    where = [f"{_TIME_COL[fact]} >= ? AND {_TIME_COL[fact]} <= ?"]
    for item in spec.filters:
        if item.dimension not in catalog.dimensions or not _IDENT.match(item.dimension):
            raise CompileError(f"Unknown filter {item.dimension}.")
        if not catalog.allows(item.dimension, fact):
            raise CompileError(f"{catalog.dimension(item.dimension).label} does not apply to {metric.label}.")
        if not item.values:
            raise CompileError(f"Filter {item.dimension} has no values.")
        slots = ", ".join("?" for _ in item.values)
        where.append(f"{catalog.filter_expr(item.dimension, fact)} IN ({slots})")
        for value in item.values:
            params.append(catalog.bind(item.dimension, value))

    sql = ["SELECT", "  " + ",\n  ".join(select_parts), _FROM[fact], "WHERE " + " AND ".join(where)]
    if spec.group_by:
        positions = ", ".join(str(i) for i in range(1, len(spec.group_by) + 1))
        sql.append(f"GROUP BY {positions}")
        if spec.order_by == "month":
            position = spec.group_by.index("month") + 1
            sql.append(f"ORDER BY {position} ASC")
        else:
            direction = "ASC" if spec.order == "asc" else "DESC"
            sql.append(f"ORDER BY {len(spec.group_by) + 1} {direction}")
    if spec.limit is not None:
        sql.append(f"LIMIT {spec.limit}")
    return "\n".join(sql), params
