from fleetline.generate import (
    CARDS_PER_CUSTOMER,
    PLANT_TXN_COUNT,
    REGIONS,
    build_dataset,
    month_dates,
)


def _total(frames) -> float:
    return round(sum(row["amount"] for row in frames["transactions"]), 2)


def test_seed_rebuilds_the_same_portfolio():
    first = build_dataset(42)
    second = build_dataset(42)
    other = build_dataset(99)
    assert _total(first) == _total(second)
    assert _total(first) != _total(other)
    assert first["transactions"][0]["txn_id"] == "T0000001"
    assert first["transactions"][-1]["txn_id"] == f"T-PLANT-{PLANT_TXN_COUNT:03d}"


def test_row_counts_match_the_generator():
    frames = build_dataset(42)
    months = len(month_dates())
    fleets = 36
    assert months == 18
    assert len(frames["customers"]) == fleets + 1
    assert len(frames["cards"]) == fleets * CARDS_PER_CUSTOMER + 1
    state_count = sum(len(states) for states in REGIONS.values())
    assert len(frames["merchants"]) == state_count * 4 + 1
    assert len(frames["transactions"]) == fleets * CARDS_PER_CUSTOMER * months + PLANT_TXN_COUNT
    assert len(frames["invoices"]) == (fleets + 1) * months


def test_planted_skimming_rows_are_fixed():
    frames = build_dataset(42)
    planted = [row for row in frames["transactions"] if row["txn_id"].startswith("T-PLANT")]
    assert len(planted) == PLANT_TXN_COUNT
    assert {row["fraud_type"] for row in planted} == {"Skimming"}
    assert {row["amount"] for row in planted} == {720.0}
    assert {row["merchant_id"] for row in planted} == {"M-PLANT"}
    merchant = next(row for row in frames["merchants"] if row["merchant_id"] == "M-PLANT")
    assert merchant["merchant_name"] == "Red Mesa Travel Center"
    assert merchant["state"] == "Texas"
