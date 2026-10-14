from datetime import date

from fleetline.catalog import get_catalog
from fleetline.compiler import CompileError, compile_spec
from fleetline.models import Filter, QuerySpec, TimeRange
from fleetline.service import get_state


def _spec(**overrides) -> QuerySpec:
    payload = dict(
        metric="fuel_spend",
        group_by=[],
        filters=[],
        time_range=TimeRange(start=date(2026, 1, 1), end=date(2026, 9, 30), label="this year"),
        order="desc",
        order_by="value",
        limit=None,
    )
    payload.update(overrides)
    return QuerySpec(**payload)


def test_hostile_filter_is_a_parameter_not_sql():
    hostile = "West' OR 1=1; DROP TABLE transactions; --"
    spec = _spec(filters=[Filter(dimension="region", values=[hostile])])
    sql, params = compile_spec(spec, get_catalog())
    assert "DROP" not in sql
    assert "OR 1=1" not in sql
    assert "?" in sql
    assert hostile in params


def test_unknown_metric_and_limit_are_rejected():
    catalog = get_catalog()
    try:
        compile_spec(_spec(metric="not_a_metric"), catalog)
        raise AssertionError("expected CompileError")
    except CompileError:
        pass
    try:
        compile_spec(_spec(limit=1000), catalog)
        raise AssertionError("expected CompileError")
    except CompileError:
        pass


def test_compiled_spend_runs_and_groups_by_position():
    catalog = get_catalog()
    spec = _spec(group_by=["region"], limit=5)
    sql, params = compile_spec(spec, catalog)
    assert "GROUP BY 1" in sql
    assert "LIMIT 5" in sql
    rows = get_state().store.query(sql, params)
    assert rows
    assert "region" in rows[0]
    assert isinstance(rows[0]["value"], float)
    assert rows[0]["value"] > 0
