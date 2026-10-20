import getpass
import hashlib
import json
import math
import sqlite3
from pathlib import Path

import psycopg
import sqlglot
from sqlglot import exp

from app.guardrails.sql_validator import ALLOWED_NODES


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "spider"
DB_ID = "poker_player"
ALLOWED_TABLES = {"people", "poker_player"}


def values_equal(left, right):
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(
            left, right, rel_tol=1e-9, abs_tol=1e-8
        )
    return left == right


def rows_equal(left, right):
    return len(left) == len(right) and all(
        values_equal(a, b) for a, b in zip(left, right)
    )


def results_equal(actual, expected, ordered):
    if len(actual) != len(expected):
        return False

    if ordered:
        return all(
            rows_equal(a, b) for a, b in zip(actual, expected)
        )

    # Match rows while preserving duplicate counts.
    remaining = list(expected)
    for row in actual:
        for index, candidate in enumerate(remaining):
            if rows_equal(row, candidate):
                remaining.pop(index)
                break
        else:
            return False

    return not remaining


def adapt_query(original):
    # Explicit adaptation for this inspected dataset.
    adjusted = original.replace('"Russia"', "'Russia'")
    tree = sqlglot.parse_one(adjusted, read="sqlite")

    if type(tree) is not exp.Select:
        raise ValueError("Expected a SELECT reference query")

    for identifier in tree.find_all(exp.Identifier):
        identifier.set("this", identifier.name.lower())

    for table in tree.find_all(exp.Table):
        if table.name not in ALLOWED_TABLES:
            raise ValueError(f"Unexpected reference table: {table.name}")
        table.set("db", exp.to_identifier("public"))

    unsupported = sorted({
        type(node).__name__
        for node in tree.walk()
        if type(node) not in ALLOWED_NODES
    })

    return (
        tree.sql(dialect="postgres"),
        tree.args.get("order") is not None,
        unsupported,
    )


def main():
    dev_path = DATA / "dev.json"
    source_bytes = dev_path.read_bytes()
    questions = json.loads(source_bytes)
    sqlite_path = DATA / "database" / DB_ID / f"{DB_ID}.sqlite"

    selected = [
        (index, case)
        for index, case in enumerate(questions)
        if case["db_id"] == DB_ID
    ]
    if len(selected) != 40:
        raise ValueError(f"Expected 40 questions, found {len(selected)}")

    password = getpass.getpass("sg_spider_reader password: ")
    records = []

    source = sqlite3.connect(
        sqlite_path.resolve().as_uri() + "?mode=ro",
        uri=True,
    )

    try:
        with psycopg.connect(
            host="127.0.0.1",
            port=5433,
            dbname="schemaguard_spider",
            user="sg_spider_reader",
            password=password,
            connect_timeout=5,
            options=(
                "-c default_transaction_read_only=on "
                "-c statement_timeout=5000 "
                "-c lock_timeout=1000"
            ),
        ) as connection:
            for source_index, case in selected:
                adapted, ordered, unsupported = adapt_query(case["query"])

                record = {
                    "source_index": source_index,
                    "db_id": DB_ID,
                    "question": case["question"],
                    "original_sql": case["query"],
                    "postgres_sql": adapted,
                    "ordered": ordered,
                    "unsupported_nodes": unsupported,
                    "parity": False,
                    "error_type": None,
                }

                try:
                    source_cursor = source.execute(case["query"])
                    expected = source_cursor.fetchall()
                    expected_width = len(source_cursor.description)

                    # A savepoint lets subsequent cases run after a SQL error.
                    with connection.transaction():
                        with connection.cursor() as cursor:
                            cursor.execute(adapted)
                            actual = cursor.fetchall()
                            actual_width = len(cursor.description)

                    record["parity"] = (
                        actual_width == expected_width
                        and results_equal(actual, expected, ordered)
                    )
                except (sqlite3.Error, psycopg.Error) as exc:
                    record["error_type"] = type(exc).__name__

                records.append(record)
                status = "PASS" if record["parity"] else "FAIL"
                policy = (
                    "unsupported: " + ", ".join(unsupported)
                    if unsupported else "supported"
                )
                print(
                    f"{status} source={source_index} | "
                    f"{policy} | error={record['error_type'] or '-'}"
                )
    finally:
        source.close()

    parity_count = sum(record["parity"] for record in records)
    supported_count = sum(
        not record["unsupported_nodes"] for record in records
    )

    report = {
        "dataset": "Spider 1.0 development",
        "db_id": DB_ID,
        "dev_json_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "sqlite_sha256": hashlib.sha256(
            sqlite_path.read_bytes()
        ).hexdigest(),
        "numeric_tolerance": {"relative": 1e-9, "absolute": 1e-8},
        "total_questions": len(records),
        "reference_parity_passed": parity_count,
        "structurally_supported": supported_count,
        "cases": records,
    }

    path = ROOT / "spider_reference_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nReference parity: {parity_count}/{len(records)}")
    print(f"Structurally supported: {supported_count}/{len(records)}")
    print(f"Report: {path}")

    return 0 if parity_count == len(records) else 1


if __name__ == "__main__":
    raise SystemExit(main())