from decimal import Decimal

import pytest
from sqlalchemy.exc import SQLAlchemyError
from app.execution import sql_executor
from app.guardrails.sql_validator import SQLValidationError


def test_executes_customer_spending_query():
    result = sql_executor.execute_query(
        """
        SELECT c.id, c.name, SUM(o.amount) AS total_spent
        FROM public.customers c
        JOIN public.orders o ON c.id = o.customer_id
        GROUP BY c.id, c.name
        HAVING SUM(o.amount) > 50000
        ORDER BY total_spent DESC
        """
    )

    assert result.columns == ["id", "name", "total_spent"]
    assert result.rows == [
        [3, "Rohan Mehta", Decimal("70000.00")],
        [1, "Aarav Sharma", Decimal("55000.00")],
    ]
    assert result.row_count == 2


def test_executor_rejects_delete():
    with pytest.raises(SQLValidationError):
        sql_executor.execute_query("DELETE FROM public.orders")


def test_rejects_query_above_cost_limit(monkeypatch):
    monkeypatch.setattr(sql_executor, "MAX_ESTIMATED_COST", 0.0)

    with pytest.raises(sql_executor.QueryCostError):
        sql_executor.execute_query("SELECT id FROM public.orders")


def test_connection_works_after_database_error():
    with pytest.raises(SQLAlchemyError):
        sql_executor.execute_query(
            "SELECT nonexistent_column FROM public.orders"
        )

    result = sql_executor.execute_query(
        "SELECT COUNT(*) AS order_count FROM public.orders"
    )

    assert result.rows == [[5]]