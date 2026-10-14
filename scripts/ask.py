"""Ask one question from the shell: python scripts/ask.py "fuel spend this year"."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fleetline.models import BlankQuestion  # noqa: E402
from fleetline.service import ask  # noqa: E402


def main() -> None:
    question = " ".join(sys.argv[1:]).strip() or "Top 5 customers by spend this year"
    try:
        result = ask(question)
    except BlankQuestion as exc:
        print(exc)
        sys.exit(2)
    print(result.message)
    if result.status != "answer" or result.spec is None:
        for suggestion in result.suggestions:
            print(f"- {suggestion}")
        return
    spec = result.spec
    filters = ", ".join(f"{item.dimension}={item.values}" for item in spec.filters) or "none"
    print(
        f"metric={spec.metric} group={spec.group_by or '—'} "
        f"filters={filters} time={spec.time_range.label} limit={spec.limit}"
    )
    print(result.sql)
    for row in result.rows[:15]:
        print(row)


if __name__ == "__main__":
    main()
