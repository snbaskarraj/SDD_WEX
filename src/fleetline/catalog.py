"""Load the semantic layer and reject a catalog that could compile unsafe SQL."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import yaml

from fleetline.paths import SEMANTIC_PATH

_ALLOWED_ALIASES = {
    "transactions": {"t", "c", "cd", "m"},
    "invoices": {"i", "c"},
}
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
_ALIAS = re.compile(r"\b([a-z]{1,2})\.")


def _aliases(expression: str) -> set[str]:
    return set(_ALIAS.findall(expression))


def _per_fact(node: str | dict[str, str], facts: tuple[str, ...], key: str) -> dict[str, str]:
    if isinstance(node, str):
        return {fact: node for fact in facts}
    missing = [fact for fact in facts if fact not in node]
    if missing:
        raise ValueError(f"{key} is missing an expression for {', '.join(missing)}")
    return {fact: node[fact] for fact in facts}


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    description: str
    fact: str
    expression: str
    format: str
    synonyms: tuple[str, ...]


@dataclass(frozen=True)
class Dimension:
    key: str
    label: str
    description: str
    facts: tuple[str, ...]
    expressions: dict[str, str]
    selects: dict[str, str]
    synonyms: tuple[str, ...]
    mentions: tuple[str, ...]
    value_synonyms: dict[str, str]
    value_type: str
    bind: dict[str, object]
    implied_metric: str | None

    def display_values(self) -> list[str]:
        if self.bind:
            return list(self.bind)
        seen: list[str] = []
        for value in self.value_synonyms.values():
            if value not in seen:
                seen.append(value)
        return seen


@dataclass(frozen=True)
class Example:
    area: str
    question: str


@dataclass
class Catalog:
    version: str
    metrics: dict[str, Metric]
    dimensions: dict[str, Dimension]
    examples: list[Example]
    metric_phrases: list[tuple[str, str]] = field(init=False)
    value_phrases: list[tuple[str, str, str]] = field(init=False)
    dimension_phrases: list[tuple[str, str]] = field(init=False)

    def __post_init__(self) -> None:
        self.metric_phrases = sorted(
            ((syn, metric.key) for metric in self.metrics.values() for syn in metric.synonyms),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        self.value_phrases = sorted(
            (
                (phrase, dim.key, display)
                for dim in self.dimensions.values()
                for phrase, display in dim.value_synonyms.items()
            ),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        self.dimension_phrases = sorted(
            ((syn, dim.key) for dim in self.dimensions.values() for syn in dim.synonyms),
            key=lambda item: len(item[0]),
            reverse=True,
        )

    def metric(self, key: str) -> Metric:
        try:
            return self.metrics[key]
        except KeyError as exc:
            raise KeyError(f"unknown metric {key}") from exc

    def dimension(self, key: str) -> Dimension:
        try:
            return self.dimensions[key]
        except KeyError as exc:
            raise KeyError(f"unknown dimension {key}") from exc

    def allows(self, dimension: str, fact: str) -> bool:
        return fact in self.dimension(dimension).facts

    def groupable(self, fact: str) -> list[str]:
        return [dim.label for dim in self.dimensions.values() if fact in dim.facts]

    def select_expr(self, dimension: str, fact: str) -> str:
        return self.dimension(dimension).selects[fact]

    def filter_expr(self, dimension: str, fact: str) -> str:
        return self.dimension(dimension).expressions[fact]

    def bind(self, dimension: str, display: str) -> object:
        dim = self.dimension(dimension)
        if dim.value_type == "bool":
            if display not in dim.bind:
                raise KeyError(f"{display!r} is not a {dimension} value")
            return bool(dim.bind[display])
        return display

    def lookup_value(self, phrase: str) -> tuple[str, str] | None:
        for known, dimension, display in self.value_phrases:
            if known == phrase:
                return dimension, display
        return None


def _load_metric(key: str, raw: dict) -> Metric:
    if not _IDENT.match(key):
        raise ValueError(f"metric key {key!r} is not an identifier")
    fact = raw["fact"]
    if fact not in _ALLOWED_ALIASES:
        raise ValueError(f"{key} has unknown fact {fact}")
    expression = str(raw["expression"])
    illegal = _aliases(expression) - _ALLOWED_ALIASES[fact]
    if illegal:
        raise ValueError(f"{key} uses aliases {sorted(illegal)} on {fact}")
    synonyms = tuple(str(item).lower().strip() for item in raw["synonyms"])
    return Metric(
        key=key,
        label=str(raw["label"]),
        description=str(raw["description"]),
        fact=fact,
        expression=expression,
        format=str(raw["format"]),
        synonyms=synonyms,
    )


def _load_dimension(key: str, raw: dict) -> Dimension:
    if not _IDENT.match(key):
        raise ValueError(f"dimension key {key!r} is not an identifier")
    facts = tuple(raw["facts"])
    expressions = _per_fact(raw["expression"], facts, key)
    select_node = raw.get("select", raw["expression"])
    selects = _per_fact(select_node, facts, key)
    for fact in facts:
        for label, expr in (("expression", expressions[fact]), ("select", selects[fact])):
            illegal = _aliases(expr) - _ALLOWED_ALIASES[fact]
            if illegal:
                raise ValueError(f"{key} {label} uses aliases {sorted(illegal)} on {fact}")
    synonyms = tuple(str(item).lower().strip() for item in raw.get("synonyms", []))
    mentions = tuple(str(item).lower().strip() for item in raw.get("mentions", []))
    value_synonyms = {str(k).lower().strip(): str(v) for k, v in raw.get("value_synonyms", {}).items()}
    bind = {str(k): v for k, v in raw.get("bind", {}).items()}
    value_type = str(raw.get("value_type", "string"))
    if value_type == "bool":
        missing = [display for display in value_synonyms.values() if display not in bind]
        if missing:
            raise ValueError(f"{key} values {missing} are missing from bind")
    return Dimension(
        key=key,
        label=str(raw["label"]),
        description=str(raw.get("description", "")),
        facts=facts,
        expressions=expressions,
        selects=selects,
        synonyms=synonyms,
        mentions=mentions,
        value_synonyms=value_synonyms,
        value_type=value_type,
        bind=bind,
        implied_metric=raw.get("implied_metric"),
    )


def _reject_duplicates(pairs: list[tuple[str, str]], what: str) -> None:
    seen: dict[str, str] = {}
    for phrase, owner in pairs:
        if phrase in seen:
            raise ValueError(f"duplicate {what} {phrase!r} on {seen[phrase]} and {owner}")
        seen[phrase] = owner


def load_catalog(path=SEMANTIC_PATH) -> Catalog:
    raw = yaml.safe_load(path.read_text())
    metrics = {key: _load_metric(key, body) for key, body in raw["metrics"].items()}
    dimensions = {key: _load_dimension(key, body) for key, body in raw["dimensions"].items()}
    _reject_duplicates([(syn, key) for key, metric in metrics.items() for syn in metric.synonyms], "metric synonym")
    _reject_duplicates(
        [(syn, key) for key, dim in dimensions.items() for syn in dim.synonyms],
        "dimension synonym",
    )
    _reject_duplicates(
        [(phrase, key) for key, dim in dimensions.items() for phrase in dim.value_synonyms],
        "value synonym",
    )
    for dim in dimensions.values():
        if dim.implied_metric and dim.implied_metric not in metrics:
            raise ValueError(f"{dim.key} implies unknown metric {dim.implied_metric}")
    examples = [Example(area=str(item["area"]), question=str(item["question"])) for item in raw["examples"]]
    return Catalog(
        version=str(raw["version"]),
        metrics=metrics,
        dimensions=dimensions,
        examples=examples,
    )


@lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    return load_catalog()
