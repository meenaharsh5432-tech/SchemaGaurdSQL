from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import ProgrammingError

from app.guardrails.sql_validator import SQLValidationError
from evaluation import run_spider_poker as runner


@pytest.fixture
def case():
    return {
        "source_index": 647,
        "question": "How many poker players are there?",
        "ordered": False,
    }


@pytest.fixture
def expected():
    return SimpleNamespace(columns=["count"], rows=[[5]])


def database_error():
    original = Exception("Undefined column")
    original.sqlstate = "42703"
    original.diag = SimpleNamespace(
        message_primary='column "missing" does not exist'
    )
    return ProgrammingError("SELECT missing", {}, original)


def test_correct_first_attempt_uses_benchmark_scope(
    monkeypatch, case, expected
):
    generate = Mock(return_value="SELECT COUNT(*) FROM public.poker_player")
    execute = Mock(return_value=expected)
    monkeypatch.setattr(runner, "generate", generate)
    monkeypatch.setattr(runner, "execute_query", execute)
    benchmark_engine = object()

    result = runner.run_case(
        case, expected, benchmark_engine, object(), "{}"
    )

    assert result["correct"] is True
    assert result["repair_attempts"] == 0
    assert result["attempts"][0]["status"] == "correct"
    assert execute.call_args.kwargs == {
        "db_engine": benchmark_engine,
        "allowed_tables": frozenset({"people", "poker_player"}),
        "expected_user": "sg_spider_reader",
        "expected_database": "schemaguard_spider",
    }


def test_database_error_triggers_repair(monkeypatch, case, expected):
    bad_sql = "SELECT missing FROM public.poker_player"
    good_sql = "SELECT COUNT(*) FROM public.poker_player"

    generate = Mock(side_effect=[bad_sql, good_sql])
    execute = Mock(side_effect=[database_error(), expected])
    monkeypatch.setattr(runner, "generate", generate)
    monkeypatch.setattr(runner, "execute_query", execute)

    result = runner.run_case(case, expected, object(), object(), "{}")

    assert result["correct"] is True
    assert result["repair_attempts"] == 1
    assert result["attempts"][0]["sqlstate"] == "42703"
    assert result["attempts"][1]["status"] == "correct"

    repair_arguments = generate.call_args_list[1].args
    assert repair_arguments[3] == bad_sql
    assert 'column "missing" does not exist' in repair_arguments[4]


def test_repairs_stop_after_three_retries(monkeypatch, case, expected):
    generate = Mock(return_value="SELECT missing FROM public.poker_player")
    execute = Mock(side_effect=database_error())
    monkeypatch.setattr(runner, "generate", generate)
    monkeypatch.setattr(runner, "execute_query", execute)

    result = runner.run_case(case, expected, object(), object(), "{}")

    assert result["correct"] is False
    assert result["repair_attempts"] == 3
    assert generate.call_count == 4
    assert execute.call_count == 4
    assert len(result["attempts"]) == 4
    assert result["error_type"] == "ProgrammingError"


def test_validator_rejection_is_not_repaired(monkeypatch, case, expected):
    generate = Mock(return_value="SELECT invalid_sql")
    execute = Mock(
        side_effect=SQLValidationError("Unsupported SQL structure")
    )
    monkeypatch.setattr(runner, "generate", generate)
    monkeypatch.setattr(runner, "execute_query", execute)

    result = runner.run_case(case, expected, object(), object(), "{}")

    assert result["correct"] is False
    assert result["repair_attempts"] == 0
    assert result["error_type"] == "SQLValidationError"
    assert generate.call_count == 1


def test_wrong_result_is_recorded_without_repair(
    monkeypatch, case, expected
):
    generate = Mock(return_value="SELECT COUNT(*) FROM public.people")
    execute = Mock(
        return_value=SimpleNamespace(columns=["count"], rows=[[7]])
    )
    monkeypatch.setattr(runner, "generate", generate)
    monkeypatch.setattr(runner, "execute_query", execute)

    result = runner.run_case(case, expected, object(), object(), "{}")

    assert result["correct"] is False
    assert result["error_type"] is None
    assert result["attempts"][0]["status"] == "result_mismatch"
    assert generate.call_count == 1