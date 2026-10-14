# Design notes

The contract — API shapes, interpreter rules, test scenarios, and planted stories — is `README.md`. This file is how the code is split and where the safety boundary sits.

## Request path

1. `api.ask` rejects a blank question with `400` and an unknown JSON field with `422`.
2. `service.ask` loads the previous spec for `session_id`, if one was answered.
3. `nlu.resolve` either returns a clarification or a complete `QuerySpec`.
4. `compiler.compile_spec` turns that spec into one `SELECT` and a parameter list.
5. `store.query` runs it on DuckDB.
6. `narrate.narrate` builds the sentence from the rows. The service adds chart metadata and stores the spec.

A clarification does not replace the stored spec. “What’s the weather?” in the middle of a conversation leaves the last answer in place.

## SQL boundary

`compiler.py` is the only module that concatenates SQL text.

- Metric expressions and dimension expressions are read from `semantic/metrics.yaml`.
- Dimension keys used as aliases must match `^[a-z_][a-z0-9_]*$`.
- Filter values are bound with `?`. They are never interpolated.
- `LIMIT` is an `int` in `1..100` chosen by the interpreter, not a string from the request.
- `GROUP BY` and `ORDER BY` use select positions (`GROUP BY 1`, `ORDER BY 2`), so aliases cannot clash with source columns.
- Transactions join customers, cards, and merchants. Invoices join customers only. The catalog loader rejects an invoice expression that references `t`, `cd`, or `m`.

The interpreter never returns SQL. The UI shows the compiled statement so a reviewer can see there is no second definition of “fraud losses”.

## Interpreter

`nlu.py` is a span masker:

1. Strip a time phrase (`timeparse.py`) so “last 3 months” cannot also become a month breakdown.
2. Mark the longest metric phrase. If another metric’s phrase is still unmarked, clarify.
3. Mark breakdown phrases (`by`, `per`, `which`, `top N`, `monthly`, `over time`).
4. Mark “diesel vs unleaded” as a product filter plus a product breakdown.
5. Mark catalog values (region, product, SecureFuel, skimming, …).
6. Mark state names, then attach them to merchant state or customer state once the fact table is known.
7. Anything still unmarked, other than function words, clarifies.

Follow-ups call the same parser and `apply_followup`, which merges onto the previous spec using rule 9 in the README.

State names are not in the YAML value lists because the same word maps to two columns. That mapping is the one special case in the interpreter, and it is covered by `tests/test_nlu.py`.

## Sessions

`service.AppState.sessions` maps a session id to a `QuerySpec`. The UI stores the id in a variable and sends it back. “New conversation” drops it. The cap is 200 sessions; past that, the oldest id is discarded.

## Synthetic data

`generate.build_dataset(seed)` is a pure function: one `random.Random(seed)`, loops in a fixed order, no `set` iteration. `generate_dataset` writes five parquet files.

The July 2026 skimming rows are appended after the random transactions with fixed ids, amounts, and flags. Story tests do not depend on a random draw landing in Texas.

`store.ensure_data` generates into `FLEETLINE_DATA_DIR` or `data/` when any parquet file is missing. Tests point the env var at a temp directory.

## UI

`src/fleetline/static/` is served by the same process as the API. The Ask view posts to `/api/ask`. The Definitions view reads `/api/catalog`, so the page cannot drift from the YAML.

Charts are drawn as SVG in the page. There is no frontend build and no CDN request.

## Tests

Unit tests for time, catalog, compiler, and the interpreter do not need the parquet files. Story and API tests use one session-scoped dataset so the portfolio is generated once per `pytest` run.
