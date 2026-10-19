import asyncio
import json
import math
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
import argparse
from app.agent import workflow
from app.execution.sql_executor import execute_query
import hashlib

from app.agent.generator import SYSTEM_PROMPT
from app.cache.query_cache import POLICY_VERSION
from app.config import settings

EVALUATION_DIR = Path(__file__).resolve().parent


def normalize_value(value):
    # Compare equivalent database numbers consistently.
    # Text remains text: "001" must not become the number 1.
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    return value


def results_match(actual, expected, ordered):
    if len(actual.columns) != len(expected.columns):
        return False

    actual_rows = [
        tuple(normalize_value(value) for value in row)
        for row in actual.rows
    ]
    expected_rows = [
        tuple(normalize_value(value) for value in row)
        for row in expected.rows
    ]

    if ordered:
        return actual_rows == expected_rows

    # Counter preserves duplicate-row counts.
    return Counter(actual_rows) == Counter(expected_rows)


async def evaluate_case(case, expected):
    generation_calls = 0
    original_generate = workflow.generate_sql

    async def counted_generate(*args, **kwargs):
        nonlocal generation_calls
        generation_calls += 1
        return await original_generate(*args, **kwargs)

    started = perf_counter()
    correct = False
    generated_sql = None
    error_type = None

    try:
        # Sequential evaluation: count initial generation and repair calls.
        with patch.object(workflow, "generate_sql", counted_generate):
            outcome = await workflow.run_query(case["question"])

        generated_sql = outcome.result.sql
        correct = results_match(
            outcome.result,
            expected,
            case["ordered"],
        )
    except Exception as exc:
        # Record failure and continue evaluating the remaining cases.
        error_type = type(exc).__name__

    latency_ms = round((perf_counter() - started) * 1000, 2)
    repair_attempts = max(0, generation_calls - 1)

    return {
        "id": case["id"],
        "correct": correct,
        "repair_attempts": repair_attempts,
        "latency_ms": latency_ms,
        "generated_sql": generated_sql,
        "error_type": error_type,
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="cases.json")
    args = parser.parse_args()

    cases_path = EVALUATION_DIR / args.cases
    cases = json.loads(cases_path.read_text(encoding="utf-8"))

    if not cases:
        raise ValueError("Evaluation cases must not be empty")

    # Verify all reference queries before spending time on the model.
    # Reference SQL uses the same guarded, read-only executor.
    expected_results = [
        execute_query(case["gold_sql"])
        for case in cases
    ]

    
    

    records = []

    for case, expected in zip(cases, expected_results):
        record = await evaluate_case(case, expected)
        records.append(record)

        status = "PASS" if record["correct"] else "FAIL"
        print(
            f"{status} {record['id']} | "
            f"repairs={record['repair_attempts']} | "
            f"{record['latency_ms']:.2f} ms | "
            f"error={record['error_type'] or '-'}"
        )

    total = len(records)
    correct = sum(record["correct"] for record in records)
    first_attempt_correct = sum(
        record["correct"] and record["repair_attempts"] == 0
        for record in records
    )
    retried = sum(
        record["repair_attempts"] > 0 for record in records
    )
    repaired_correctly = sum(
        record["correct"] and record["repair_attempts"] > 0
        for record in records
    )

    latencies = sorted(record["latency_ms"] for record in records)
    p95_index = math.ceil(0.95 * total) - 1

    metrics = {
        "total_cases": total,
        "correct_cases": correct,
        "execution_accuracy_pct": round(100 * correct / total, 2),
        "first_attempt_accuracy_pct": round(
            100 * first_attempt_correct / total, 2
        ),
        "retry_rate_pct": round(100 * retried / total, 2),
        "repair_success_rate_pct": (
            round(100 * repaired_correctly / retried, 2)
            if retried else None
        ),
        "error_cases": sum(
            record["error_type"] is not None for record in records
        ),
        "p95_latency_ms": latencies[p95_index],
    }

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "direct_workflow_without_result_cache",
        "configuration": {
            "model": settings.ollama_model,
            "policy_version": POLICY_VERSION,
            "system_prompt_sha256": hashlib.sha256(
                SYSTEM_PROMPT.encode("utf-8")
            ).hexdigest(),
            "cases_file": cases_path.name,
            "cases_sha256": hashlib.sha256(
                json.dumps(
                    cases,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        },
        "metrics": metrics,
        "cases": records,
    }

    report_path = EVALUATION_DIR / f"{cases_path.stem}_report.json"
    report_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\nMetrics:")
    print(json.dumps(metrics, indent=2))
    print(f"\nReport saved to: {report_path}")
    return 0 if correct == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))