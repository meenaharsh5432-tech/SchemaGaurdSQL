import asyncio
import os

import pytest

from app.agent import workflow
from app.agent.generator import generate_sql as real_generate_sql
from app.database import engine


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_LLM_TESTS") != "1",
    reason="Requires running PostgreSQL and Ollama",
)
def test_real_model_repairs_undefined_column(monkeypatch):
    generation_calls = 0
    feedback_received = []

    async def controlled_generate_sql(
        question,
        *,
        previous_sql=None,
        error_feedback=None,
    ):
        nonlocal generation_calls
        generation_calls += 1

        if generation_calls == 1:
            # Valid SELECT structure, but this column does not exist.
            from app.schemas.query import GeneratedSQL

            return GeneratedSQL(
                sql="SELECT customer_name FROM public.customers"
            )

        feedback_received.append(error_feedback)

        # All repair attempts use the real local model.
        return await real_generate_sql(
            question,
            previous_sql=previous_sql,
            error_feedback=error_feedback,
        )

    monkeypatch.setattr(
        workflow,
        "generate_sql",
        controlled_generate_sql,
    )

    outcome = asyncio.run(
        workflow.run_query(
            "List every customer's name, ordered by customer ID ascending. "
            "Return only the name column."
        )
    )

    # Build the expected answer independently from the current database.
    with engine.connect() as connection:
        expected_rows = [
            list(row)
            for row in connection.exec_driver_sql(
                "SELECT name FROM public.customers ORDER BY id LIMIT 100"
            )
        ]

    assert 1 <= outcome.repair_count <= 3
    assert generation_calls == outcome.repair_count + 1
    assert "42703" in feedback_received[0]
    assert len(outcome.result.columns) == 1
    assert outcome.result.rows == expected_rows

    print(f"\nRepair count: {outcome.repair_count}")
    print(f"Final SQL: {outcome.result.sql}")
    print(f"Rows: {outcome.result.rows}")