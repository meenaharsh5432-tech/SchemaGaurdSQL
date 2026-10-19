import asyncio
from dataclasses import dataclass

from sqlalchemy.exc import DBAPIError
import logging

logger = logging.getLogger(__name__)
from app.agent.generator import generate_sql
from app.execution.sql_executor import QueryResult, execute_query


MAX_REPAIRS = 3

REPAIRABLE_SQLSTATES = {
    "42601",  # Syntax error
    "42703",  # Undefined column
    "42702",  # Ambiguous column
    "42803",  # Grouping error
    "42P01",  # Undefined table or missing FROM reference
}


class RepairExhaustedError(RuntimeError):
    """The query still fails after the permitted repairs."""


@dataclass
class WorkflowResult:
    result: QueryResult
    repair_count: int
    schema_version: str | None


async def run_query(question: str) -> WorkflowResult:
    previous_sql = None
    error_feedback = None

    for repair_count in range(MAX_REPAIRS + 1):
        generated = await generate_sql(
            question,
            previous_sql=previous_sql,
            error_feedback=error_feedback,
        )

        try:
            result = await asyncio.to_thread(
                execute_query,
                generated.sql,
            )

        except DBAPIError as exc:
            sqlstate = getattr(exc.orig, "sqlstate", None)
            diagnostic = getattr(exc.orig, "diag", None)
            message = getattr(diagnostic, "message_primary", None)

            logger.warning(
                "Attempt %s/4 failed | SQLSTATE=%s | Error=%s | SQL=%s",
                repair_count + 1,
                sqlstate,
                message,
                generated.sql,
            )

            sqlstate = getattr(exc.orig, "sqlstate", None)

            if sqlstate not in REPAIRABLE_SQLSTATES:
                raise

            if repair_count == MAX_REPAIRS:
                raise RepairExhaustedError(
                    "SQL still failed after three repair attempts"
                ) from exc

            diagnostic = getattr(exc.orig, "diag", None)
            message = getattr(diagnostic, "message_primary", None)

            # Send only a bounded primary diagnostic, not the full exception.
            error_feedback = (
                f"SQLSTATE {sqlstate}: "
                f"{str(message or 'PostgreSQL rejected the query')[:1000]}"
            )

            previous_sql = generated.sql

        else:
            return WorkflowResult(
                result=result,
                repair_count=repair_count,
                schema_version=generated.schema_version,
            )

    raise RuntimeError("Unexpected workflow termination")