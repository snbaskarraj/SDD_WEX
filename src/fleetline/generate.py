"""Seeded fleet-card portfolio. Same seed, same rows.

The July 2026 skimming sales are appended after the random transactions
so the story does not depend on a coin flip.
"""

from __future__ import annotations

import random
from datetime import date
from pathlib import Path

import duckdb

from fleetline.constants import DATA_END, DATA_START
from fleetline.paths import data_dir

PLANT_TXN_COUNT = 30
PLANT_AMOUNT = 720.0
PLANT_MONTH = date(2026, 7, 15)
CARDS_PER_CUSTOMER = 8

REGIONS: dict[str, list[str]] = {
    "Northeast": ["New York", "Massachusetts", "Pennsylvania", "New Jersey"],
    "Southeast": ["Florida", "Georgia", "North Carolina", "Virginia"],
    "Midwest": ["Illinois", "Ohio", "Michigan", "Minnesota"],
    "Southwest": ["Texas", "Arizona", "New Mexico", "Oklahoma"],
    "West": ["California", "Washington", "Colorado", "Oregon"],
}
ABBR = {
    "New York": "NY",
    "Massachusetts": "MA",
    "Pennsylvania": "PA",
    "New Jersey": "NJ",
    "Florida": "FL",
    "Georgia": "GA",
    "North Carolina": "NC",
    "Virginia": "VA",
    "Illinois": "IL",
    "Ohio": "OH",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Texas": "TX",
    "Arizona": "AZ",
    "New Mexico": "NM",
    "Oklahoma": "OK",
    "California": "CA",
    "Washington": "WA",
    "Colorado": "CO",
    "Oregon": "OR",
}
INDUSTRIES = ["Transportation", "Construction", "Energy", "Technology", "Government", "Retail"]
SEGMENTS = ["Small", "Mid-market", "Enterprise"]
PROGRAMS = ["Universal", "Regional", "EV Fleet"]
CATEGORIES = ["Truck stop", "Retail fuel", "Cardlock", "Depot"]
BRANDS = ["Red Mesa", "Harborline", "Prairie Stop", "Summit Fuel"]
FLEET_A = [
    "Northstar",
    "Cedar Ridge",
    "Brightline",
    "Harbor",
    "Prairie",
    "Summit",
    "Bluebird",
    "Ironwood",
    "Lakeshore",
    "Copperline",
    "High Plains",
    "Glassford",
]
FLEET_B = ["Logistics", "Hauling", "Construction", "Freight", "Services", "Transport"]

TABLES = {
    "customers": [
        ("customer_id", "VARCHAR"),
        ("customer_name", "VARCHAR"),
        ("industry", "VARCHAR"),
        ("segment", "VARCHAR"),
        ("region", "VARCHAR"),
        ("state", "VARCHAR"),
        ("card_program", "VARCHAR"),
    ],
    "cards": [
        ("card_id", "VARCHAR"),
        ("customer_id", "VARCHAR"),
        ("vehicle_class", "VARCHAR"),
        ("fuel_type", "VARCHAR"),
        ("secure_fuel", "BOOLEAN"),
    ],
    "merchants": [
        ("merchant_id", "VARCHAR"),
        ("merchant_name", "VARCHAR"),
        ("category", "VARCHAR"),
        ("state", "VARCHAR"),
        ("region", "VARCHAR"),
        ("in_network", "BOOLEAN"),
    ],
    "transactions": [
        ("txn_id", "VARCHAR"),
        ("txn_date", "DATE"),
        ("customer_id", "VARCHAR"),
        ("card_id", "VARCHAR"),
        ("merchant_id", "VARCHAR"),
        ("product", "VARCHAR"),
        ("gallons", "DOUBLE"),
        ("amount", "DOUBLE"),
        ("unit_price", "DOUBLE"),
        ("auth_status", "VARCHAR"),
        ("decline_reason", "VARCHAR"),
        ("fraud_flag", "BOOLEAN"),
        ("fraud_type", "VARCHAR"),
    ],
    "invoices": [
        ("invoice_id", "VARCHAR"),
        ("customer_id", "VARCHAR"),
        ("invoice_month", "DATE"),
        ("billed_amount", "DOUBLE"),
        ("paid_amount", "DOUBLE"),
        ("days_past_due", "INTEGER"),
        ("writeoff_amount", "DOUBLE"),
    ],
}


def month_dates() -> list[date]:
    dates: list[date] = []
    year, month = DATA_START.year, DATA_START.month
    while (year, month) <= (DATA_END.year, DATA_END.month):
        dates.append(date(year, month, 15))
        month += 1
        if month == 13:
            month = 1
            year += 1
    return dates


def _fuel_type(industry: str, card_index: int) -> str:
    if industry == "Technology":
        return "EV" if card_index % 2 == 0 else "Gasoline"
    if card_index % 20 == 0:
        return "EV"
    if card_index % 7 == 0:
        return "Hybrid"
    if card_index % 2 == 0:
        return "Diesel"
    return "Gasoline"


def _vehicle_class(card_index: int) -> str:
    return ("Heavy", "Medium", "Light")[card_index % 3]


def _line_item(fuel_type: str, industry: str, merchant_region: str, rng: random.Random):
    if fuel_type == "EV":
        base = 220.0 if industry == "Technology" else 35.0
        amount = round(base * (0.9 + rng.random() * 0.2), 2)
        return "Electricity", 0.0, amount, None
    if fuel_type == "Hybrid":
        product = "Unleaded"
    elif fuel_type == "Diesel":
        product = "DEF" if rng.random() < 0.08 else "Diesel"
    else:
        product = "Premium" if rng.random() < 0.2 else "Unleaded"
    if product == "Diesel" and merchant_region == "West":
        price = 4.50 + rng.random() * 0.10
    elif product == "Diesel":
        price = 3.60 + rng.random() * 0.10
    elif product == "Unleaded":
        price = 3.15 + rng.random() * 0.15
    elif product == "Premium":
        price = 3.85 + rng.random() * 0.15
    else:
        price = 2.85 + rng.random() * 0.10
    gallons = round(10 + rng.random() * (70 if fuel_type == "Diesel" else 18), 3)
    amount = round(price * gallons, 2)
    return product, gallons, amount, round(price, 4)


def _days_past_due(segment: str, month_index: int) -> int:
    if segment == "Enterprise":
        return 60 if month_index % 3 == 0 else 10
    if segment == "Mid-market":
        return 45 if month_index % 9 == 0 else 5
    return 4


def build_dataset(seed: int = 42) -> dict[str, list[dict]]:
    region_names = list(REGIONS)
    names = [f"{a} {b}" for a in FLEET_A for b in FLEET_B][:36]
    customers: list[dict] = []
    for index, name in enumerate(names):
        region = region_names[index % len(region_names)]
        states = REGIONS[region]
        customers.append(
            {
                "customer_id": f"C{index + 1:03d}",
                "customer_name": name,
                "industry": INDUSTRIES[index % len(INDUSTRIES)],
                "segment": SEGMENTS[index % len(SEGMENTS)],
                "region": region,
                "state": states[index % len(states)],
                "card_program": PROGRAMS[index % len(PROGRAMS)],
            }
        )
    customers.append(
        {
            "customer_id": "C-PLANT",
            "customer_name": "Cinder Basin Transport",
            "industry": "Transportation",
            "segment": "Enterprise",
            "region": "Southwest",
            "state": "Texas",
            "card_program": "Universal",
        }
    )

    cards: list[dict] = []
    card_number = 1
    for customer in customers:
        if customer["customer_id"] == "C-PLANT":
            continue
        for offset in range(CARDS_PER_CUSTOMER):
            cards.append(
                {
                    "card_id": f"K{card_number:04d}",
                    "customer_id": customer["customer_id"],
                    "vehicle_class": _vehicle_class(offset),
                    "fuel_type": _fuel_type(customer["industry"], offset),
                    "secure_fuel": offset % 5 < 2,
                }
            )
            card_number += 1
    cards.append(
        {
            "card_id": "K-PLANT",
            "customer_id": "C-PLANT",
            "vehicle_class": "Heavy",
            "fuel_type": "Diesel",
            "secure_fuel": False,
        }
    )

    merchants: list[dict] = []
    merchant_number = 1
    for region, states in REGIONS.items():
        for state in states:
            for category in CATEGORIES:
                brand = BRANDS[(merchant_number - 1) % len(BRANDS)]
                merchants.append(
                    {
                        "merchant_id": f"M{merchant_number:03d}",
                        "merchant_name": f"{brand} {category} {ABBR[state]}-{merchant_number}",
                        "category": category,
                        "state": state,
                        "region": region,
                        "in_network": merchant_number % 4 != 0,
                    }
                )
                merchant_number += 1
    merchants.append(
        {
            "merchant_id": "M-PLANT",
            "merchant_name": "Red Mesa Travel Center",
            "category": "Truck stop",
            "state": "Texas",
            "region": "Southwest",
            "in_network": True,
        }
    )

    by_customer = {row["customer_id"]: row for row in customers}
    by_region: dict[str, list[dict]] = {}
    other_merchants = [row for row in merchants if row["merchant_id"] != "M-PLANT"]
    for merchant in other_merchants:
        by_region.setdefault(merchant["region"], []).append(merchant)

    rng = random.Random(seed)
    transactions: list[dict] = []
    txn_number = 1
    decline_reasons = ["insufficient_funds", "limit_exceeded", "suspected_fraud", "card_inactive"]
    for card in cards:
        if card["card_id"] == "K-PLANT":
            continue
        customer = by_customer[card["customer_id"]]
        local = by_region[customer["region"]]
        for txn_date in month_dates():
            pool = local if rng.random() < 0.85 else other_merchants
            merchant = pool[rng.randrange(len(pool))]
            product, gallons, amount, unit_price = _line_item(
                card["fuel_type"], customer["industry"], merchant["region"], rng
            )
            declined = rng.random() < 0.07
            fraud = False
            fraud_type = None
            reason = None
            if declined:
                reason = decline_reasons[rng.randrange(len(decline_reasons))]
            else:
                probability = 0.0004 if card["secure_fuel"] else 0.001
                if rng.random() < probability:
                    fraud = True
                    fraud_type = "Card not present" if rng.random() < 0.5 else "Skimming"
            transactions.append(
                {
                    "txn_id": f"T{txn_number:07d}",
                    "txn_date": txn_date,
                    "customer_id": customer["customer_id"],
                    "card_id": card["card_id"],
                    "merchant_id": merchant["merchant_id"],
                    "product": product,
                    "gallons": gallons,
                    "amount": amount,
                    "unit_price": unit_price,
                    "auth_status": "Declined" if declined else "Approved",
                    "decline_reason": reason,
                    "fraud_flag": fraud,
                    "fraud_type": fraud_type,
                }
            )
            txn_number += 1

    for index in range(PLANT_TXN_COUNT):
        transactions.append(
            {
                "txn_id": f"T-PLANT-{index + 1:03d}",
                "txn_date": PLANT_MONTH,
                "customer_id": "C-PLANT",
                "card_id": "K-PLANT",
                "merchant_id": "M-PLANT",
                "product": "Diesel",
                "gallons": 150.0,
                "amount": PLANT_AMOUNT,
                "unit_price": round(PLANT_AMOUNT / 150.0, 4),
                "auth_status": "Approved",
                "decline_reason": None,
                "fraud_flag": True,
                "fraud_type": "Skimming",
            }
        )

    billed_for = {"Small": 20000.0, "Mid-market": 45000.0, "Enterprise": 90000.0}
    invoices: list[dict] = []
    invoice_number = 1
    for customer in customers:
        for month_index, txn_date in enumerate(month_dates()):
            past_due = _days_past_due(customer["segment"], month_index)
            billed = billed_for[customer["segment"]]
            paid = billed if past_due <= 30 else round(billed * 0.5, 2)
            writeoff = 1000.0 if customer["segment"] == "Enterprise" and month_index % 9 == 0 else 0.0
            invoices.append(
                {
                    "invoice_id": f"I{invoice_number:05d}",
                    "customer_id": customer["customer_id"],
                    "invoice_month": date(txn_date.year, txn_date.month, 1),
                    "billed_amount": billed,
                    "paid_amount": paid,
                    "days_past_due": past_due,
                    "writeoff_amount": writeoff,
                }
            )
            invoice_number += 1

    return {
        "customers": customers,
        "cards": cards,
        "merchants": merchants,
        "transactions": transactions,
        "invoices": invoices,
    }


def _write_table(directory: Path, table: str, rows: list[dict]) -> None:
    columns = TABLES[table]
    con = duckdb.connect()
    column_sql = ", ".join(f"{name} {kind}" for name, kind in columns)
    con.execute(f"CREATE TABLE {table} ({column_sql})")
    placeholders = ", ".join("?" for _ in columns)
    values = [tuple(row[name] for name, _kind in columns) for row in rows]
    con.executemany(f"INSERT INTO {table} VALUES ({placeholders})", values)
    destination = (directory / f"{table}.parquet").as_posix().replace("'", "''")
    con.execute(f"COPY {table} TO '{destination}' (FORMAT PARQUET)")
    con.close()


def generate_dataset(directory: Path | None = None, seed: int = 42) -> dict[str, int]:
    target = directory or data_dir()
    target.mkdir(parents=True, exist_ok=True)
    frames = build_dataset(seed)
    for table, rows in frames.items():
        _write_table(target, table, rows)
    return {table: len(rows) for table, rows in frames.items()}


def main() -> None:
    counts = generate_dataset()
    for table, count in counts.items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()
