import logging
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings


logger = logging.getLogger(__name__)

audit_engine = create_engine(
    settings.audit_database_url.get_secret_value(),
    pool_pre_ping=True,
    pool_size=2,
    max_overflow=0,
    pool_timeout=2,
    connect_args={"connect_timeout": 3},
    hide_parameters=True,
)


INSERT_EVENT = text(
    """
    INSERT INTO audit.query_events (
        request_id,
        endpoint,
        question,
        generated_sql,
        status,
        http_status,
        cache_hit,
        executed,
        repair_count,
        row_count,
        total_duration_ms,
        database_duration_ms,
        schema_version,
        model,
        error_code
    )
    VALUES (
        :request_id,
        :endpoint,
        :question,
        :generated_sql,
        :status,
        :http_status,
        :cache_hit,
        :executed,
        :repair_count,
        :row_count,
        :total_duration_ms,
        :database_duration_ms,
        :schema_version,
        :model,
        :error_code
    )
    """
)


def write_audit_event(
    *,
    request_id: UUID,
    status: str,
    http_status: int,
    total_duration_ms: float,
    endpoint: str = "/query",
    question: str | None = None,
    generated_sql: str | None = None,
    cache_hit: bool = False,
    executed: bool = False,
    repair_count: int | None = None,
    row_count: int | None = None,
    database_duration_ms: float | None = None,
    schema_version: str | None = None,
    model: str | None = None,
    error_code: str | None = None,
) -> bool:
    parameters = {
        "request_id": request_id,
        "endpoint": endpoint,
        "question": question,
        "generated_sql": generated_sql,
        "status": status,
        "http_status": http_status,
        "cache_hit": cache_hit,
        "executed": executed,
        "repair_count": repair_count,
        "row_count": row_count,
        "total_duration_ms": total_duration_ms,
        "database_duration_ms": database_duration_ms,
        "schema_version": schema_version,
        "model": model,
        "error_code": error_code,
    }

    try:
        with audit_engine.begin() as connection:
            connection.execute(INSERT_EVENT, parameters)

    except SQLAlchemyError as exc:
        logger.error(
            "Audit insert failed; request_id=%s; exception=%s",
            request_id,
            type(exc).__name__,
        )
        return False

    return True