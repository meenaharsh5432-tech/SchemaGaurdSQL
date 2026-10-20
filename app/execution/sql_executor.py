from dataclasses import dataclass
from time import perf_counter
from typing import Any

from sqlalchemy.engine import Engine

from app.database import engine
from app.guardrails.sql_validator import MAX_ROWS, validate_sql


MAX_ESTIMATED_COST = 10000.0


class QueryCostError(ValueError):
    """The estimated query cost exceeds the configured threshold."""


@dataclass
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    estimated_cost: float
    duration_ms: float


def execute_query(
    sql: str,
    *,
    db_engine: Engine | None = None,
    allowed_tables: frozenset[str] | None = None,
    expected_user: str = "sg_reader",
    expected_database: str | None = None,
) -> QueryResult:
    # Default calls preserve the application's existing behavior.
    if allowed_tables is None:
        checked_sql = validate_sql(sql)
    else:
        checked_sql = validate_sql(
            sql,
            allowed_tables=allowed_tables,
        )

    selected_engine = engine if db_engine is None else db_engine
    started = perf_counter()

    with selected_engine.begin() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        connection.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
        connection.exec_driver_sql("SET LOCAL lock_timeout = '1s'")
        connection.exec_driver_sql("SET LOCAL search_path = pg_catalog")

        database_user = connection.exec_driver_sql(
            "SELECT current_user"
        ).scalar_one()

        if database_user != expected_user:
            raise RuntimeError(
                "Query execution requires the configured read-only role"
            )

        if expected_database is not None:
            database_name = connection.exec_driver_sql(
                "SELECT current_database()"
            ).scalar_one()

            if database_name != expected_database:
                raise RuntimeError(
                    "Query execution connected to an unexpected database"
                )

        plan = connection.exec_driver_sql(
            "EXPLAIN (FORMAT JSON) " + checked_sql
        ).scalar_one()

        estimated_cost = float(plan[0]["Plan"]["Total Cost"])

        if estimated_cost > MAX_ESTIMATED_COST:
            raise QueryCostError(
                f"Estimated cost {estimated_cost:.2f} exceeds "
                f"the limit {MAX_ESTIMATED_COST:.2f}"
            )

        result = connection.exec_driver_sql(checked_sql)

        try:
            columns = list(result.keys())
            fetched_rows = result.fetchmany(MAX_ROWS + 1)
        finally:
            result.close()

        if len(fetched_rows) > MAX_ROWS:
            raise RuntimeError("Query exceeded the enforced row limit")

        rows = [list(row) for row in fetched_rows]

    return QueryResult(
        sql=checked_sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        estimated_cost=estimated_cost,
        duration_ms=round((perf_counter() - started) * 1000, 2),
    )