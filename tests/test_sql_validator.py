import pytest
import sqlglot
from sqlalchemy.exc import SQLAlchemyError
from app.guardrails.sql_validator import (
    SQLValidationError,
    validate_sql,
)


def test_accepts_customer_spending_query():
    sql = """
        SELECT c.id, c.name, SUM(o.amount) AS total_spent
        FROM public.customers c
        JOIN public.orders o ON c.id = o.customer_id
        GROUP BY c.id, c.name
        HAVING SUM(o.amount) > 50000
    """

    checked = validate_sql(sql)
    tree = sqlglot.parse_one(checked, read="postgres")

    assert tree.args["limit"].expression.this == "100"
    assert "SUM(o.amount)" in checked


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(5, "5"), (100, "100"), (5000, "100")],
)
def test_limits_returned_rows(requested, expected):
    checked = validate_sql(
        f"SELECT id FROM public.orders LIMIT {requested}"
    )
    tree = sqlglot.parse_one(checked, read="postgres")

    assert tree.args["limit"].expression.this == expected


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "DELETE FROM public.orders",
        "SELECT * FROM public.orders; DROP TABLE public.orders",
        "SELECT * FROM public.secret_payroll",
        "SELECT * FROM pg_catalog.pg_tables",
        "SELECT * FROM orders",
        "SELECT pg_sleep(30) FROM public.orders",
        "SELECT public.sum(amount) FROM public.orders",
        "SELECT * INTO public.copy_orders FROM public.orders",
        "SELECT * FROM public.orders FOR UPDATE",
        "WITH x AS (SELECT * FROM public.orders) SELECT * FROM x",
        "SELECT * FROM (SELECT * FROM public.orders) AS x",
        "SELECT * FROM public.orders LIMIT -1",
    ],
)
def test_rejects_unsupported_queries(sql):
    with pytest.raises(SQLValidationError):
        validate_sql(sql)