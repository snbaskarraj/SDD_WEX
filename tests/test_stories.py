from fleetline.generate import PLANT_AMOUNT, PLANT_TXN_COUNT
from fleetline.service import ask


def _by(rows, key):
    return {row[key]: row["value"] for row in rows}


def test_july_texas_skimming_dominates():
    result = ask("How much did we lose to skimming in Texas in July 2026?")
    assert result.status == "answer"
    assert result.rows[0]["value"] >= PLANT_TXN_COUNT * PLANT_AMOUNT
    assert "Skimming" in result.message
    assert "Texas" in result.message


def test_southwest_fraud_peaks_in_july_2026():
    result = ask("Monthly fraud losses in the Southwest")
    assert result.status == "answer"
    peak = max(result.rows, key=lambda row: row["value"])
    assert peak["month"] == "2026-07"
    assert "2026-07" in result.message


def test_follow_up_to_texas_keeps_the_july_spike():
    first = ask("Monthly fraud losses in the Southwest")
    second = ask("and for Texas", session_id=first.session_id)
    assert second.spec is not None
    assert second.spec.group_by == ["month"]
    peak = max(second.rows, key=lambda row: row["value"])
    assert peak["month"] == "2026-07"


def test_securefuel_fraud_rate_is_lower():
    result = ask("Fraud rate by SecureFuel status")
    rates = _by(result.rows, "secure_fuel")
    assert rates["Standard"] > rates["SecureFuel"]


def test_technology_leads_ev_share():
    result = ask("Which industry has the highest EV share?")
    assert result.rows[0]["industry"] == "Technology"
    assert "Technology" in result.message


def test_enterprise_is_the_most_delinquent():
    result = ask("Delinquency rate by segment")
    rates = _by(result.rows, "segment")
    assert rates["Enterprise"] > rates["Mid-market"] > rates["Small"]
    assert result.rows[0]["segment"] == "Enterprise"


def test_west_diesel_costs_more_than_midwest_diesel():
    west = ask("Diesel price per gallon in the West")
    midwest = ask("Diesel price per gallon in the Midwest")
    assert west.rows[0]["value"] > midwest.rows[0]["value"] + 0.4
