import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.exc import ProgrammingError

from app.agent import workflow
from app.execution.sql_executor import QueryResult
from app.guardrails.sql_validator import SQLValidationError
from app.schemas.query import GeneratedSQL


def make_database_error(code: str) -> ProgrammingError:
    original = Exception("Simulated PostgreSQL error")
    original.sqlstate = code
    original.diag = SimpleNamespace(
        message_primary='column "customer_name" does not exist'
    )

    return ProgrammingError(
        statement="SELECT customer_name FROM public.customers",
        params=None,
        orig=original,
    )


def test_repairs_undefined_column(monkeypatch):
    bad_sql = "SELECT customer_name FROM public.customers"
    good_sql = "SELECT name FROM public.customers"

    generator = AsyncMock(
        side_effect=[
            GeneratedSQL(sql=bad_sql),
            GeneratedSQL(sql=good_sql),
        ]
    )

    expected = QueryResult(
        sql=good_sql + " LIMIT 100",
        columns=["name"],
        rows=[["Aarav Sharma"]],
        row_count=1,
        estimated_cost=1.0,
        duration_ms=1.0,
    )

    executor = Mock(
        side_effect=[make_database_error("42703"), expected]
    )

    monkeypatch.setattr(workflow, "generate_sql", generator)
    monkeypatch.setattr(workflow, "execute_query", executor)

    outcome = asyncio.run(workflow.run_query("List customer names"))

    assert outcome.repair_count == 1
    assert outcome.result is expected
    assert executor.call_count == 2

    repair_arguments = generator.await_args_list[1].kwargs
    assert repair_arguments["previous_sql"] == bad_sql
    assert "42703" in repair_arguments["error_feedback"]


def test_stops_after_three_repairs(monkeypatch):
    generator = AsyncMock(
        return_value=GeneratedSQL(
            sql="SELECT customer_name FROM public.customers"
        )
    )
    executor = Mock(side_effect=make_database_error("42703"))

    monkeypatch.setattr(workflow, "generate_sql", generator)
    monkeypatch.setattr(workflow, "execute_query", executor)

    with pytest.raises(workflow.RepairExhaustedError):
        asyncio.run(workflow.run_query("List customer names"))

    assert generator.await_count == 4
    assert executor.call_count == 4


@pytest.mark.parametrize("code", ["42501", "57014", "55P03"])
def test_does_not_retry_operational_or_permission_errors(monkeypatch, code):
    generator = AsyncMock(
        return_value=GeneratedSQL(sql="SELECT id FROM public.orders")
    )
    executor = Mock(side_effect=make_database_error(code))

    monkeypatch.setattr(workflow, "generate_sql", generator)
    monkeypatch.setattr(workflow, "execute_query", executor)

    with pytest.raises(ProgrammingError):
        asyncio.run(workflow.run_query("List order IDs"))

    assert generator.await_count == 1
    assert executor.call_count == 1


def test_repaired_sql_still_passes_through_executor(monkeypatch):
    generator = AsyncMock(
        side_effect=[
            GeneratedSQL(sql="SELECT customer_name FROM public.customers"),
            GeneratedSQL(sql="DELETE FROM public.customers"),
        ]
    )

    executor = Mock(
        side_effect=[
            make_database_error("42703"),
            SQLValidationError("Only SELECT queries are supported"),
        ]
    )

    monkeypatch.setattr(workflow, "generate_sql", generator)
    monkeypatch.setattr(workflow, "execute_query", executor)

    with pytest.raises(SQLValidationError):
        asyncio.run(workflow.run_query("List customer names"))

    assert generator.await_count == 2
    assert executor.call_args.args[0] == "DELETE FROM public.customers"