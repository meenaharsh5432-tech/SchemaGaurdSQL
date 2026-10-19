import json
from pathlib import Path

import sqlglot
from sqlglot import exp

from app.retrieval.retriever import schema_retriever
from app.retrieval.schema_cache import schema_cache


def main():
    directory = Path(__file__).resolve().parent
    snapshot = schema_cache.get()
    total_tables = len(json.loads(snapshot.prompt)["tables"])

    passed = 0
    total = 0
    selected_counts = []

    for filename in (
        "cases.json",
        "holdout_cases.json",
        "expanded_cases.json",
    ):
        cases = json.loads(
            (directory / filename).read_text(encoding="utf-8")
        )

        for case in cases:
            gold = sqlglot.parse_one(
                case["gold_sql"],
                read="postgres",
            )
            required = {
                f"{table.db}.{table.name}"
                for table in gold.find_all(exp.Table)
            }

            retrieved = schema_retriever.retrieve(
                case["question"],
                snapshot,
            )
            selected = set(retrieved.selected_tables)
            missing = required - selected

            total += 1
            passed += not missing
            selected_counts.append(len(selected))

            status = "PASS" if not missing else "FAIL"
            print(
                f"{status} {case['id']} | "
                f"selected={len(selected)}/{total_tables} | "
                f"missing={sorted(missing)}"
            )

    print(f"\nReference-table coverage: {passed}/{total}")
    print(
        "Average selected tables: "
        f"{sum(selected_counts) / total:.2f}/{total_tables}"
    )

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())