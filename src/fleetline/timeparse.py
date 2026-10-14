"""Time phrases anchored on the portfolio as-of date, not the wall clock."""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from fleetline.constants import AS_OF
from fleetline.models import TimeRange

_FULL = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
_MONTHS: dict[str, int] = {name.lower(): i for i, name in enumerate(_FULL, start=1)}
for _short, _idx in (
    ("jan", 1),
    ("feb", 2),
    ("mar", 3),
    ("apr", 4),
    ("may", 5),
    ("jun", 6),
    ("jul", 7),
    ("aug", 8),
    ("sep", 9),
    ("sept", 9),
    ("oct", 10),
    ("nov", 11),
    ("dec", 12),
):
    _MONTHS[_short] = _idx

_NUM_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}
_MONTH_ALT = "|".join(sorted(_MONTHS, key=len, reverse=True))
_NUM_ALT = r"\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"


def _shift_months(anchor: date, delta: int) -> date:
    month_index = anchor.month - 1 + delta
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _quarter(year: int, quarter: int) -> tuple[date, date]:
    start_month = 3 * (quarter - 1) + 1
    end_month = start_month + 2
    last_day = calendar.monthrange(year, end_month)[1]
    return date(year, start_month, 1), date(year, end_month, last_day)


def _cut(text: str, start: int, end: int) -> str:
    return re.sub(r"\s+", " ", f"{text[:start]} {text[end:]}").strip()


def _n_months(match: re.Match[str]) -> TimeRange:
    raw = match.group(1)
    count = int(raw) if raw.isdigit() else _NUM_WORDS[raw]
    start = _shift_months(date(AS_OF.year, AS_OF.month, 1), -(count - 1))
    return TimeRange(start=start, end=AS_OF, label=f"last {count} months")


def _named_month(match: re.Match[str]) -> TimeRange:
    month = _MONTHS[match.group(1)]
    year = int(match.group(2))
    last_day = calendar.monthrange(year, month)[1]
    return TimeRange(
        start=date(year, month, 1),
        end=date(year, month, last_day),
        label=f"{_FULL[month - 1]} {year}",
    )


def _quarter_phrase(match: re.Match[str]) -> TimeRange:
    quarter = int(match.group(1))
    year = int(match.group(2))
    start, end = _quarter(year, quarter)
    return TimeRange(start=start, end=end, label=f"Q{quarter} {year}")


def _calendar_year(match: re.Match[str]) -> TimeRange:
    year = int(match.group(1))
    start = date(year, 1, 1)
    end = date(year, 12, 31)
    if start > AS_OF:
        end = start
    else:
        end = min(end, AS_OF)
    return TimeRange(start=start, end=end, label=str(year))


def _fixed(label: str, start: date, end: date):
    def build(_match: re.Match[str]) -> TimeRange:
        return TimeRange(start=start, end=end, label=label)

    return build


def _this_quarter() -> tuple[date, date]:
    quarter = (AS_OF.month - 1) // 3 + 1
    return _quarter(AS_OF.year, quarter)


def _last_quarter() -> tuple[date, date]:
    quarter = (AS_OF.month - 1) // 3 + 1
    if quarter == 1:
        return _quarter(AS_OF.year - 1, 4)
    return _quarter(AS_OF.year, quarter - 1)


def _last_month() -> tuple[date, date]:
    first_this = date(AS_OF.year, AS_OF.month, 1)
    end = first_this - timedelta(days=1)
    return date(end.year, end.month, 1), end


def _this_month() -> tuple[date, date]:
    return date(AS_OF.year, AS_OF.month, 1), AS_OF


_THIS_Q = _this_quarter()
_LAST_Q = _last_quarter()
_LAST_M = _last_month()
_THIS_M = _this_month()

# Longer and more specific phrases are collected together; the earliest span in
# the question wins, so "July 2026" is not swallowed by a nearby "2026".
_PATTERNS: list[tuple[re.Pattern[str], object]] = [
    (re.compile(rf"\b(?:last|past)\s+({_NUM_ALT})\s+months?\b"), _n_months),
    (re.compile(r"\blast month\b"), _fixed("last month", _LAST_M[0], _LAST_M[1])),
    (re.compile(r"\bthis month\b"), _fixed("this month", _THIS_M[0], _THIS_M[1])),
    (re.compile(r"\blast quarter\b"), _fixed("last quarter", _LAST_Q[0], _LAST_Q[1])),
    (re.compile(r"\bthis quarter\b"), _fixed("this quarter", _THIS_Q[0], _THIS_Q[1])),
    (re.compile(r"\blast year\b"), _fixed("last year", date(AS_OF.year - 1, 1, 1), date(AS_OF.year - 1, 12, 31))),
    (re.compile(r"\b(?:year to date|ytd|this year)\b"), _fixed("this year", date(AS_OF.year, 1, 1), AS_OF)),
    (re.compile(r"\bq([1-4])\s*(20\d{2})\b"), _quarter_phrase),
    (re.compile(rf"\b(?:in\s+|during\s+)?({_MONTH_ALT})\s+(20\d{{2}})\b"), _named_month),
    (re.compile(r"\b(?:in\s+|during\s+)?(20\d{2})\b"), _calendar_year),
]


def extract_time(text: str, *, as_of: date = AS_OF) -> tuple[TimeRange | None, str]:
    """Return the first time phrase and the question with that phrase removed.

    `as_of` is accepted so tests can show the anchor is the argument, not today.
    The built-in phrases are defined for the portfolio as-of date.
    """
    del as_of  # phrases are compiled against the portfolio anchor
    found: list[tuple[int, int, re.Match[str], object]] = []
    for pattern, builder in _PATTERNS:
        match = pattern.search(text)
        if match:
            found.append((match.start(), -(match.end() - match.start()), match, builder))
    if not found:
        return None, text
    found.sort()
    _start, _neg_len, match, builder = found[0]
    return builder(match), _cut(text, match.start(), match.end())
