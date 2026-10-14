"""Turn a question into a QuerySpec, or ask for clarification.

The phrase matcher marks spans it understands. Anything left over, other than
function words, refuses the question. Follow-ups edit the previous spec.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from fleetline.catalog import Catalog, get_catalog
from fleetline.constants import DEFAULT_TIME_LABEL, DATA_END, DATA_START
from fleetline.models import Filter, QuerySpec, TimeRange
from fleetline.timeparse import extract_time

DEFAULT_GROUP_LIMIT = 25
RANK_LIMIT = 10
GEO_DIMENSIONS = {"region", "state", "merchant_state"}

STOP = frozenset(
    """
    a an the of to in on by per each with without from into over under across
    during through about what which who how much many did do does was were is
    are be been our we you me my your their show tell give please total overall
    compare versus vs between has have had this that those these only just same
    now filter down break and or for at as than then also it its if up not no
    yes all any some more less very really can could would should will us them
    within inside outside around after before bought sold buy sell using use
    used based where when fleet portfolio card cards status type lose lost loss
    losses last past next previous current ask compute calculate display list
    rank ranked ranking against hello hi hey there
    highest lowest most least largest biggest best worst top bottom first peak peaked
    """.split()
)

OFF_TOPIC = (
    "weather",
    "forecast",
    "recipe",
    "football",
    "basketball",
    "baseball",
    "soccer",
    "nba",
    "nfl",
    "stock price",
    "share price",
    "joke",
    "poem",
    "lyrics",
    "password",
    "who is",
    "write a",
    "song",
)

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
}
_NUM_ALT = r"\d+|one|two|three|four|five|six|seven|eight|nine|ten"
_GROUP_PREFIX = r"(?:broken down by|break (?:that|it|this) down by|by|per|each)"
_INCREMENTAL = re.compile(
    r"^(and|what about|how about|break|same|now|only|just|filter|show that)\b"
)
_CUSTOMER_STATE = re.compile(r"\b(customer state|fleet state|home state)\b")

# State names are applied after the fact table is known: merchant state for
# card questions, customer state for invoices.
STATES: dict[str, str] = {
    "new york": "New York",
    "ny": "New York",
    "massachusetts": "Massachusetts",
    "ma": "Massachusetts",
    "pennsylvania": "Pennsylvania",
    "pa": "Pennsylvania",
    "new jersey": "New Jersey",
    "nj": "New Jersey",
    "florida": "Florida",
    "fl": "Florida",
    "georgia": "Georgia",
    "ga": "Georgia",
    "north carolina": "North Carolina",
    "nc": "North Carolina",
    "virginia": "Virginia",
    "va": "Virginia",
    "illinois": "Illinois",
    "il": "Illinois",
    "ohio": "Ohio",
    "oh": "Ohio",
    "michigan": "Michigan",
    "mi": "Michigan",
    "minnesota": "Minnesota",
    "mn": "Minnesota",
    "texas": "Texas",
    "tx": "Texas",
    "arizona": "Arizona",
    "az": "Arizona",
    "new mexico": "New Mexico",
    "nm": "New Mexico",
    "oklahoma": "Oklahoma",
    "california": "California",
    "ca": "California",
    "washington": "Washington",
    "wa": "Washington",
    "colorado": "Colorado",
    "co": "Colorado",
    "oregon": "Oregon",
}
STATE_PHRASES = sorted(STATES.items(), key=lambda item: len(item[0]), reverse=True)


class Text:
    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.mask = bytearray(len(raw))

    def overlaps(self, start: int, end: int) -> bool:
        return any(self.mask[start:end])

    def occupy(self, start: int, end: int) -> None:
        for index in range(start, end):
            self.mask[index] = 1

    def find_all(self, phrase: str) -> list[tuple[int, int]]:
        if not phrase:
            return []
        pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)")
        return [
            (match.start(), match.end())
            for match in pattern.finditer(self.raw)
            if not self.overlaps(match.start(), match.end())
        ]

    def leftovers(self) -> list[str]:
        visible = "".join(" " if self.mask[index] else char for index, char in enumerate(self.raw))
        words = re.findall(r"[a-z][a-z0-9+\-/]*", visible)
        return [word for word in words if word not in STOP and not word.isdigit() and len(word) > 3]


@dataclass
class Partial:
    metric: str | None = None
    ambiguous: list[str] = field(default_factory=list)
    groups: list[tuple[str, str]] = field(default_factory=list)
    filters: dict[str, list[str]] = field(default_factory=dict)
    states: list[str] = field(default_factory=list)
    time_range: TimeRange | None = None
    time_set: bool = False
    order: str = "desc"
    order_set: bool = False
    limit: int | None = None
    limit_set: bool = False
    force_customer_state: bool = False
    leftovers: list[str] = field(default_factory=list)

    def add_group(self, key: str, synonym: str) -> None:
        if any(existing == key for existing, _syn in self.groups):
            return
        if len(self.groups) >= 2:
            return
        self.groups.append((key, synonym))

    def add_filter(self, dimension: str, value: str) -> None:
        values = self.filters.setdefault(dimension, [])
        if value not in values:
            values.append(value)


@dataclass
class Resolution:
    status: str
    message: str = ""
    suggestions: list[str] = field(default_factory=list)
    spec: QuerySpec | None = None


def normalize(question: str) -> str:
    text = question.lower().strip()
    text = text.replace("’", "'").replace("“", " ").replace("”", " ")
    text = text.replace("–", " ").replace("—", " ")
    text = re.sub(r"\bwhat's\b", "what is", text)
    text = text.replace("'", "")
    text = re.sub(r"[?!.,;:()]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _suggestions(catalog: Catalog) -> list[str]:
    return [example.question for example in catalog.examples[:4]]


def _clarify(catalog: Catalog, message: str) -> Resolution:
    return Resolution(status="clarify", message=message, suggestions=_suggestions(catalog))


def _off_topic(text: str) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) for phrase in OFF_TOPIC)


def _default_time() -> TimeRange:
    return TimeRange(start=DATA_START, end=DATA_END, label=DEFAULT_TIME_LABEL)


def _window(
    group_by: list[str],
    *,
    order: str,
    order_set: bool,
    limit: int | None,
    limit_set: bool,
) -> tuple[int | None, str, str]:
    if limit_set and limit is not None:
        limit = max(1, min(100, limit))
    if not group_by:
        return None, "value", order
    if "month" in group_by and not order_set:
        return (limit if limit_set else None), "month", "desc"
    if limit_set:
        return limit, "value", order
    if order_set:
        return RANK_LIMIT, "value", order
    return DEFAULT_GROUP_LIMIT, "value", "desc"


def _parse(norm: str, catalog: Catalog) -> Partial:
    partial = Partial()
    partial.force_customer_state = bool(_CUSTOMER_STATE.search(norm))
    time_range, rest = extract_time(norm)
    partial.time_range = time_range
    partial.time_set = time_range is not None
    text = Text(rest)

    matches: list[tuple[int, str, int, int]] = []
    for phrase, key in catalog.metric_phrases:
        for start, end in text.find_all(phrase):
            matches.append((end - start, key, start, end))
    if matches:
        best_len = max(item[0] for item in matches)
        best_keys = {key for length, key, _s, _e in matches if length == best_len}
        if len(best_keys) > 1:
            partial.ambiguous = sorted(best_keys)
        else:
            partial.metric = next(iter(best_keys))
            for phrase, key in catalog.metric_phrases:
                if key != partial.metric:
                    continue
                for start, end in text.find_all(phrase):
                    text.occupy(start, end)

    for phrase, key in catalog.dimension_phrases:
        prefix = re.compile(rf"\b{_GROUP_PREFIX}\s+{re.escape(phrase)}\b")
        for match in prefix.finditer(text.raw):
            if text.overlaps(match.start(), match.end()):
                continue
            text.occupy(match.start(), match.end())
            partial.add_group(key, phrase)
        which = re.compile(rf"\bwhich\s+{re.escape(phrase)}\b")
        for match in which.finditer(text.raw):
            if text.overlaps(match.start(), match.end()):
                continue
            text.occupy(match.start(), match.end())
            partial.add_group(key, phrase)
        ranked = re.compile(
            rf"\b(top|bottom|first|highest|lowest)\s+({_NUM_ALT})\s+{re.escape(phrase)}\b"
        )
        for match in ranked.finditer(text.raw):
            if text.overlaps(match.start(), match.end()):
                continue
            text.occupy(match.start(), match.end())
            partial.add_group(key, phrase)
            raw_limit = match.group(2)
            partial.limit = int(raw_limit) if raw_limit.isdigit() else _NUM_WORDS[raw_limit]
            partial.limit_set = True
            partial.order = "asc" if match.group(1) in {"bottom", "lowest"} else "desc"
            partial.order_set = True

    for dimension in catalog.dimensions.values():
        for phrase in sorted(dimension.mentions, key=len, reverse=True):
            for start, end in text.find_all(phrase):
                text.occupy(start, end)
                partial.add_group(dimension.key, phrase)

    versus = re.search(r"\b([a-z][a-z-]*)\s+(?:vs\.?|versus)\s+([a-z][a-z-]*)\b", text.raw)
    if versus and not text.overlaps(versus.start(), versus.end()):
        left = catalog.lookup_value(versus.group(1))
        right = catalog.lookup_value(versus.group(2))
        if left and right and left[0] == right[0]:
            partial.add_filter(left[0], left[1])
            partial.add_filter(right[0], right[1])
            partial.add_group(left[0], "vs")
            text.occupy(versus.start(1), versus.end(1))
            text.occupy(versus.start(2), versus.end(2))

    for phrase, dimension, display in catalog.value_phrases:
        for start, end in text.find_all(phrase):
            text.occupy(start, end)
            partial.add_filter(dimension, display)

    for phrase, display in STATE_PHRASES:
        for start, end in text.find_all(phrase):
            text.occupy(start, end)
            if display not in partial.states:
                partial.states.append(display)

    for phrase, key in catalog.dimension_phrases:
        for start, end in text.find_all(phrase):
            text.occupy(start, end)
            partial.add_group(key, phrase)

    if re.search(r"\b(bottom|lowest|least|smallest|worst)\b", text.raw):
        partial.order = "asc"
        partial.order_set = True
    elif re.search(r"\b(top|highest|most|largest|biggest|best|which)\b", text.raw):
        partial.order = "desc"
        partial.order_set = True

    partial.leftovers = text.leftovers()
    return partial


def _rewrite_groups(partial: Partial, fact: str) -> list[str]:
    rewritten: list[str] = []
    for key, synonym in partial.groups:
        if (
            key == "state"
            and synonym == "state"
            and fact == "transactions"
            and not partial.force_customer_state
        ):
            key = "merchant_state"
        if key not in rewritten:
            rewritten.append(key)
    return rewritten[:2]


def _attach_states(partial: Partial, fact: str) -> None:
    if not partial.states:
        return
    if fact == "invoices" or partial.force_customer_state:
        dimension = "state"
    else:
        dimension = "merchant_state"
    for name in partial.states:
        partial.add_filter(dimension, name)


def _implied_metric(partial: Partial, catalog: Catalog) -> str | None:
    implied = {
        catalog.dimension(dimension).implied_metric
        for dimension in partial.filters
        if catalog.dimension(dimension).implied_metric
    }
    implied.discard(None)
    if len(implied) == 1:
        return next(iter(implied))
    return None


def _filters_from(mapping: dict[str, list[str]]) -> list[Filter]:
    return [Filter(dimension=key, values=list(values)) for key, values in sorted(mapping.items())]


def merge_filters(old: list[Filter], new: dict[str, list[str]]) -> list[Filter]:
    merged = {item.dimension: list(item.values) for item in old}
    if any(dimension in GEO_DIMENSIONS for dimension in new):
        for dimension in GEO_DIMENSIONS:
            if dimension not in new:
                merged.pop(dimension, None)
    for dimension, values in new.items():
        merged[dimension] = list(values)
    return _filters_from(merged)


def _incompatible(group_by: list[str], filters: list[Filter], fact: str, catalog: Catalog) -> str | None:
    bad: list[str] = []
    for key in list(group_by) + [item.dimension for item in filters]:
        if key not in catalog.dimensions or not catalog.allows(key, fact):
            label = catalog.dimension(key).label if key in catalog.dimensions else key
            if label not in bad:
                bad.append(label)
    if not bad:
        return None
    options = ", ".join(catalog.groupable(fact)[:8])
    joined = ", ".join(bad)
    return f"{joined} doesn't apply to this metric. You can break it down by {options}."


def resolve(question: str, previous: QuerySpec | None = None, catalog: Catalog | None = None) -> Resolution:
    catalog = catalog or get_catalog()
    norm = normalize(question)
    if not norm:
        return _clarify(catalog, "Ask about spend, fraud, price, mix, or delinquency.")
    if _off_topic(norm):
        return _clarify(
            catalog,
            "I answer questions about this synthetic fleet portfolio: spend, fraud, price, mix, and delinquency.",
        )

    partial = _parse(norm, catalog)
    if partial.ambiguous:
        labels = ", ".join(catalog.metric(key).label for key in partial.ambiguous)
        return _clarify(catalog, f"That matches more than one metric ({labels}). Name the one you want.")
    if partial.leftovers:
        words = ", ".join(partial.leftovers)
        return _clarify(
            catalog,
            f"I don't know what to do with {words}. Name a metric such as fuel spend, fraud losses, or delinquency rate.",
        )

    incremental = bool(_INCREMENTAL.match(norm))
    use_previous = previous is not None and (incremental or partial.metric is None)
    implied = _implied_metric(partial, catalog)
    if partial.metric:
        metric_key = partial.metric
    elif use_previous and previous is not None:
        metric_key = previous.metric
    elif implied:
        metric_key = implied
    else:
        metric_key = None
    if metric_key is None:
        return _clarify(
            catalog,
            "Which metric should I use? Try fuel spend, fraud losses, price per gallon, or delinquency rate.",
        )

    metric = catalog.metric(metric_key)
    _attach_states(partial, metric.fact)
    group_by = _rewrite_groups(partial, metric.fact)
    group_explicit = bool(partial.groups)

    if use_previous and previous is not None:
        if group_explicit:
            limit, order_by, order = _window(
                group_by,
                order=partial.order,
                order_set=partial.order_set,
                limit=partial.limit,
                limit_set=partial.limit_set,
            )
        else:
            group_by = list(previous.group_by)
            if any(dimension in GEO_DIMENSIONS for dimension in partial.filters):
                group_by = [key for key in group_by if key not in GEO_DIMENSIONS]
            if group_by != list(previous.group_by) and not group_by:
                limit, order_by, order = None, "value", "desc"
            elif partial.limit_set:
                limit = max(1, min(100, partial.limit or 1))
                order = partial.order
                order_by = "value"
            elif partial.order_set:
                limit = previous.limit
                order = partial.order
                order_by = "value"
            else:
                limit = previous.limit
                order = previous.order
                order_by = previous.order_by
        filters = merge_filters(previous.filters, partial.filters)
        time_range = partial.time_range if partial.time_set else previous.time_range
    else:
        limit, order_by, order = _window(
            group_by,
            order=partial.order,
            order_set=partial.order_set,
            limit=partial.limit,
            limit_set=partial.limit_set,
        )
        filters = _filters_from(partial.filters)
        time_range = partial.time_range if partial.time_set else _default_time()

    problem = _incompatible(group_by, filters, metric.fact, catalog)
    if problem:
        return _clarify(catalog, problem)

    spec = QuerySpec(
        metric=metric_key,
        group_by=group_by,
        filters=filters,
        time_range=time_range,
        order="asc" if order == "asc" else "desc",
        order_by="month" if order_by == "month" else "value",
        limit=limit,
    )
    return Resolution(status="answer", spec=spec)
