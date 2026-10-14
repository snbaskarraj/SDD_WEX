from fleetline.nlu import resolve
from fleetline.service import ask


def answered(question, previous=None):
    result = resolve(question, previous)
    assert result.status == "answer", result.message
    return result.spec


def test_and_for_texas_drops_a_region_breakdown():
    first = answered("Fuel spend by region this year")
    second = answered("and for Texas", first)
    assert second.metric == "fuel_spend"
    assert second.group_by == []
    assert [(item.dimension, item.values) for item in second.filters] == [("merchant_state", ["Texas"])]
    assert second.time_range.label == "this year"
    assert second.limit is None


def test_break_that_down_replaces_the_breakdown():
    first = answered("Fuel spend by region this year")
    second = answered("break that down by product", first)
    assert second.group_by == ["product"]
    assert second.filters == []
    assert second.time_range.label == "this year"
    assert second.metric == "fuel_spend"
    assert second.limit == 25


def test_what_about_replaces_only_the_metric():
    first = answered("Fuel spend by region this year")
    second = answered("what about fraud losses", first)
    assert second.metric == "fraud_losses"
    assert second.group_by == ["region"]
    assert second.time_range.label == "this year"
    assert second.limit == 25


def test_last_quarter_keeps_the_breakdown():
    first = answered("Fuel spend by region this year")
    second = answered("last quarter", first)
    assert second.metric == "fuel_spend"
    assert second.group_by == ["region"]
    assert second.time_range.label == "last quarter"
    assert second.limit == first.limit


def test_texas_keeps_a_month_breakdown_and_replaces_region():
    first = answered("Monthly fraud losses in the Southwest")
    second = answered("and for Texas", first)
    assert second.metric == "fraud_losses"
    assert second.group_by == ["month"]
    assert second.order_by == "month"
    assert [(item.dimension, item.values) for item in second.filters] == [("merchant_state", ["Texas"])]
    assert second.limit is None


def test_top_customers_stay_ranked_inside_texas():
    first = answered("Top 5 customers by spend this year")
    second = answered("and for Texas", first)
    assert second.group_by == ["customer"]
    assert second.limit == 5
    assert [(item.dimension, item.values) for item in second.filters] == [("merchant_state", ["Texas"])]


def test_follow_up_without_a_session_asks_for_a_metric():
    result = resolve("and for Texas")
    assert result.status == "clarify"


def test_a_full_question_does_not_keep_the_previous_filters():
    first = answered("Fuel spend in Texas this year")
    second = answered("Top 5 customers by spend this year", first)
    assert second.filters == []
    assert second.group_by == ["customer"]
    assert second.limit == 5


def test_weather_does_not_erase_the_session():
    first = ask("Fuel spend this year")
    assert first.status == "answer"
    weather = ask("What's the weather in Texas?", session_id=first.session_id)
    assert weather.status == "clarify"
    follow = ask("and for Texas", session_id=first.session_id)
    assert follow.status == "answer"
    assert follow.spec is not None
    assert follow.spec.metric == "fuel_spend"
    assert follow.spec.filters[0].dimension == "merchant_state"
    assert follow.spec.filters[0].values == ["Texas"]
