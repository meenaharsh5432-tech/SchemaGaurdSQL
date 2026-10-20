import pytest

from app.guardrails.sql_validator import (
    SQLValidationError,
    validate_sql,
)


BENCHMARK_TABLES = frozenset({"people", "poker_player"})


def test_benchmark_accepts_its_own_tables():
    checked = validate_sql(
        "SELECT name FROM public.people",
        allowed_tables=BENCHMARK_TABLES,
    )
    assert "LIMIT 100" in checked


def test_benchmark_rejects_application_tables():
    with pytest.raises(SQLValidationError):
        validate_sql(
            "SELECT name FROM public.customers",
            allowed_tables=BENCHMARK_TABLES,
        )


def test_benchmark_override_does_not_change_application_policy():
    validate_sql(
        "SELECT name FROM public.people",
        allowed_tables=BENCHMARK_TABLES,
    )

    with pytest.raises(SQLValidationError):
        validate_sql("SELECT name FROM public.people")

    validate_sql("SELECT name FROM public.customers")


def test_empty_override_denies_all_tables():
    with pytest.raises(SQLValidationError):
        validate_sql(
            "SELECT name FROM public.customers",
            allowed_tables=frozenset(),
        )