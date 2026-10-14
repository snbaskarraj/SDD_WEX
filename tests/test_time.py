from datetime import date

from fleetline.timeparse import extract_time


def _range(phrase: str):
    found, rest = extract_time(phrase)
    assert found is not None, phrase
    return found, rest


def test_this_year_is_clipped_to_as_of():
    found, rest = _range("fuel spend this year")
    assert found.start == date(2026, 1, 1)
    assert found.end == date(2026, 9, 30)
    assert found.label == "this year"
    assert "year" not in rest


def test_year_to_date_matches_this_year():
    ytd, _ = _range("spend ytd")
    phrase, _ = _range("spend year to date")
    assert ytd.start == phrase.start == date(2026, 1, 1)
    assert ytd.end == phrase.end == date(2026, 9, 30)


def test_last_year_is_calendar_2025():
    found, _ = _range("spend last year")
    assert (found.start, found.end) == (date(2025, 1, 1), date(2025, 12, 31))
    assert found.label == "last year"


def test_quarters_around_30_sep_2026():
    current, _ = _range("spend this quarter")
    previous, _ = _range("spend last quarter")
    assert (current.start, current.end) == (date(2026, 7, 1), date(2026, 9, 30))
    assert (previous.start, previous.end) == (date(2026, 4, 1), date(2026, 6, 30))
    assert current.label == "this quarter"
    assert previous.label == "last quarter"


def test_last_three_months_and_last_month():
    three, rest = _range("fraud losses in the last 3 months")
    words, _ = _range("fraud losses last three months")
    last, _ = _range("fraud losses last month")
    assert three.start == words.start == date(2026, 7, 1)
    assert three.end == date(2026, 9, 30)
    assert three.label == "last 3 months"
    assert "month" not in rest
    assert (last.start, last.end) == (date(2026, 8, 1), date(2026, 8, 31))


def test_named_month_and_quarter_token():
    july, rest = _range("fraud losses in july 2026")
    abbrev, _ = _range("fraud losses jul 2026")
    quarter, _ = _range("spend q3 2026")
    assert (july.start, july.end) == (date(2026, 7, 1), date(2026, 7, 31))
    assert july.label == "July 2026"
    assert abbrev.start == july.start
    assert "july" not in rest
    assert (quarter.start, quarter.end) == (date(2026, 7, 1), date(2026, 9, 30))
    assert quarter.label == "Q3 2026"


def test_bare_year_and_last_12_months():
    year, _ = _range("spend in 2025")
    trailing, _ = _range("spend last 12 months")
    assert (year.start, year.end) == (date(2025, 1, 1), date(2025, 12, 31))
    assert (trailing.start, trailing.end) == (date(2025, 10, 1), date(2026, 9, 30))


def test_no_phrase_leaves_the_question():
    found, rest = extract_time("fuel spend by region")
    assert found is None
    assert rest == "fuel spend by region"
