from datetime import date

from fleetline.catalog import get_catalog
from fleetline.nlu import resolve


def answered(question, previous=None):
    result = resolve(question, previous)
    assert result.status == "answer", result.message
    return result.spec


def filters(spec):
    return [(item.dimension, item.values) for item in spec.filters]


def test_catalog_examples_all_resolve():
    for example in get_catalog().examples:
        result = resolve(example.question)
        assert result.status == "answer", (example.question, result.message)


def test_total_spend_this_year():
    spec = answered("Total fuel spend this year")
    assert spec.metric == "fuel_spend"
    assert spec.group_by == []
    assert spec.filters == []
    assert spec.time_range.start == date(2026, 1, 1)
    assert spec.time_range.end == date(2026, 9, 30)
    assert spec.time_range.label == "this year"
    assert spec.limit is None


def test_top_customers():
    spec = answered("Top 5 customers by spend this year")
    assert spec.metric == "fuel_spend"
    assert spec.group_by == ["customer"]
    assert spec.limit == 5
    assert spec.order == "desc"
    assert spec.order_by == "value"
    assert spec.time_range.label == "this year"


def test_fraud_by_merchant_state_in_july():
    spec = answered("Fraud losses by merchant state in July 2026")
    assert spec.metric == "fraud_losses"
    assert spec.group_by == ["merchant_state"]
    assert spec.time_range.label == "July 2026"
    assert spec.limit == 25
    assert spec.order_by == "value"


def test_bare_state_on_a_card_metric_is_the_merchant():
    spec = answered("Fraud losses by state in July 2026")
    assert spec.group_by == ["merchant_state"]


def test_monthly_southwest_is_chronological():
    spec = answered("Monthly fraud losses in the Southwest")
    assert spec.metric == "fraud_losses"
    assert spec.group_by == ["month"]
    assert filters(spec) == [("region", ["Southwest"])]
    assert spec.order_by == "month"
    assert spec.limit is None
    assert spec.time_range.label == "Apr 2025 – Sep 2026"


def test_diesel_versus_unleaded_in_the_west():
    spec = answered("Diesel vs unleaded price per gallon in the West")
    assert spec.metric == "price_per_gallon"
    assert spec.group_by == ["product"]
    assert filters(spec) == [
        ("product", ["Diesel", "Unleaded"]),
        ("region", ["West"]),
    ]
    assert spec.limit == 25


def test_which_industry_limits_to_ten():
    spec = answered("Which industry has the highest EV share?")
    assert spec.metric == "ev_share"
    assert spec.group_by == ["industry"]
    assert spec.limit == 10
    assert spec.order == "desc"


def test_delinquency_by_segment_and_by_customer_state():
    by_segment = answered("Delinquency rate by segment")
    assert by_segment.metric == "delinquency_rate"
    assert by_segment.group_by == ["segment"]
    assert by_segment.limit == 25
    by_state = answered("Delinquency rate by state")
    assert by_state.group_by == ["state"]
    in_texas = answered("Delinquency rate in Texas")
    assert filters(in_texas) == [("state", ["Texas"])]


def test_most_delinquent_segment_is_ranked():
    spec = answered("Which segment is most delinquent?")
    assert spec.metric == "delinquency_rate"
    assert spec.group_by == ["segment"]
    assert spec.limit == 10


def test_securefuel_breakdown_does_not_also_filter():
    spec = answered("Fraud rate by SecureFuel status")
    assert spec.metric == "fraud_rate"
    assert spec.group_by == ["secure_fuel"]
    assert spec.filters == []


def test_skimming_in_texas_implies_fraud_losses():
    spec = answered("How much did we lose to skimming in Texas in July 2026?")
    assert spec.metric == "fraud_losses"
    assert spec.group_by == []
    assert filters(spec) == [
        ("fraud_type", ["Skimming"]),
        ("merchant_state", ["Texas"]),
    ]
    assert spec.time_range.label == "July 2026"
    assert spec.limit is None


def test_out_of_network_spend_is_the_metric_not_a_filter():
    spec = answered("Out-of-network spend by region")
    assert spec.metric == "out_of_network_spend"
    assert spec.group_by == ["region"]
    assert spec.filters == []


def test_decline_rate_by_month_and_over_time():
    monthly = answered("Decline rate by month this year")
    assert monthly.metric == "decline_rate"
    assert monthly.group_by == ["month"]
    assert monthly.order_by == "month"
    assert monthly.limit is None
    assert monthly.time_range.label == "this year"
    trend = answered("Fuel spend over time")
    assert trend.group_by == ["month"]
    assert trend.order_by == "month"


def test_last_three_months_does_not_group_by_month():
    spec = answered("Fraud losses in the last 3 months")
    assert spec.group_by == []
    assert spec.time_range.label == "last 3 months"


def test_home_state_stays_on_the_customer():
    spec = answered("Fuel spend by home state")
    assert spec.group_by == ["state"]


def test_gallons_last_quarter():
    spec = answered("Gallons by product last quarter")
    assert spec.metric == "gallons"
    assert spec.group_by == ["product"]
    assert spec.time_range.label == "last quarter"
    assert spec.time_range.start.isoformat() == "2026-04-01"
    assert spec.time_range.end.isoformat() == "2026-06-30"


def test_unknown_words_and_two_metrics_clarify():
    moon = resolve("Fuel spend on the moon this year")
    assert moon.status == "clarify"
    assert "moon" in moon.message
    both = resolve("spend and gallons this year")
    assert both.status == "clarify"
    weather = resolve("What's the weather in Texas?")
    assert weather.status == "clarify"
    assert weather.spec is None
    missing = resolve("How much did we lose in Texas?")
    assert missing.status == "clarify"


def test_merchant_state_does_not_apply_to_delinquency():
    result = resolve("Delinquency rate by merchant state")
    assert result.status == "clarify"
    assert "Merchant state" in result.message
