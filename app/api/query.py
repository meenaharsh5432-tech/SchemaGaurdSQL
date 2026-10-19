import logging

import httpx
from fastapi import APIRouter, HTTPException
from app.agent.workflow import RepairExhaustedError, run_query
from app.agent.generator import generate_sql
from app.config import settings
from app.guardrails.sql_validator import SQLValidationError, validate_sql
import asyncio

from app.cache.query_cache import read_query_cache, write_query_cache
from app.retrieval.schema_cache import schema_cache
from app.schemas.query import GenerateSQLRequest, GenerateSQLResponse
import asyncio
from time import perf_counter
from uuid import uuid4
from app.agent.explanation import summarize_result

from fastapi import Response

from app.audit.logger import write_audit_event

from sqlalchemy.exc import (
    DBAPIError,
    SQLAlchemyError,
    TimeoutError as PoolTimeoutError,
)

from app.execution.sql_executor import QueryCostError, execute_query
from app.schemas.query import QueryResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["queries"])


@router.post("/generate-sql", response_model=GenerateSQLResponse)
async def generate_sql_endpoint(
    request: GenerateSQLRequest,
) -> GenerateSQLResponse:
    # Step 1: Generate SQL through Ollama.
    try:
        generated = await generate_sql(request.question)

    except (TimeoutError, httpx.TimeoutException):
        raise HTTPException(
            status_code=504,
            detail="SQL generation timed out",
        ) from None

    except httpx.HTTPStatusError:
        raise HTTPException(
            status_code=502,
            detail="Ollama rejected the generation request; check its server logs",
        ) from None

    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="Cannot communicate with Ollama",
        ) from None

    except SQLAlchemyError:
        logger.error("Database schema discovery failed")
        raise HTTPException(
            status_code=503,
            detail="Database schema is unavailable",
        ) from None

    except (ValueError, KeyError, TypeError):
        logger.exception("SQL generation or response validation failed")
        raise HTTPException(
            status_code=502,
            detail="Ollama returned an invalid or incomplete response",
        ) from None

    # Step 2: Validate the generated SQL.
    try:
        checked_sql = validate_sql(generated.sql)

    except SQLValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Generated SQL rejected: {exc}",
        ) from None

    # Step 3: Return the checked SQL without executing it.
    return GenerateSQLResponse(
        question=request.question,
        sql=checked_sql,
        model=settings.ollama_model,
        validated=True,
        executed=False,
    )

async def execute_query_request(
    request: GenerateSQLRequest,
) -> QueryResponse:
    started = perf_counter()

    try:
        snapshot = await asyncio.to_thread(schema_cache.get)

        cached = await asyncio.to_thread(
            read_query_cache,
            request.question,
            snapshot.version,
        )

        if cached is not None:
            return cached.model_copy(
                update={
                    "cache_hit": True,
                    "executed": False,
                    "repair_count": 0,
                    "database_duration_ms": 0.0,
                    "total_duration_ms": round(
                        (perf_counter() - started) * 1000,
                        2,
                    ),
                }
            )

        outcome = await run_query(request.question)

    except RepairExhaustedError:
        raise HTTPException(
            status_code=422,
            detail="SQL still failed after three repair attempts",
        ) from None

    except SQLValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Generated SQL rejected: {exc}",
        ) from None

    except QueryCostError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from None

    except (TimeoutError, httpx.TimeoutException):
        raise HTTPException(
            status_code=504,
            detail="SQL generation timed out",
        ) from None

    except httpx.HTTPStatusError:
        raise HTTPException(
            status_code=502,
            detail="Ollama rejected the generation request",
        ) from None

    except httpx.RequestError:
        raise HTTPException(
            status_code=503,
            detail="Cannot communicate with Ollama",
        ) from None

    except PoolTimeoutError:
        raise HTTPException(
            status_code=503,
            detail="Database connection pool is busy",
        ) from None

    except DBAPIError as exc:
        sqlstate = getattr(exc.orig, "sqlstate", None)
        logger.warning("Database query failed; SQLSTATE=%s", sqlstate)

        if sqlstate == "57014":
            raise HTTPException(
                status_code=504,
                detail="Database query was canceled or timed out",
            ) from None

        if sqlstate == "55P03":
            raise HTTPException(
                status_code=503,
                detail="Database query could not acquire a lock",
            ) from None

        if sqlstate and sqlstate.startswith("42"):
            raise HTTPException(
                status_code=422,
                detail="PostgreSQL rejected the generated SQL",
            ) from None

        raise HTTPException(
            status_code=503,
            detail="Database execution failed",
        ) from None

    except SQLAlchemyError:
        logger.error("Database execution failed")
        raise HTTPException(
            status_code=500,
            detail="Internal database execution error",
        ) from None

    result = outcome.result

    response = QueryResponse(
        question=request.question,
        sql=result.sql,
        model=settings.ollama_model,
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
        estimated_cost=result.estimated_cost,
        database_duration_ms=result.duration_ms,
        repair_count=outcome.repair_count,
        schema_version=outcome.schema_version,
        total_duration_ms=round(
            (perf_counter() - started) * 1000,
            2,
        ),
        executed=True,
        cache_hit=False,
    )

    await asyncio.to_thread(write_query_cache, response)

    # Include the cache-write attempt in this request's duration.
    return response.model_copy(
        update={
            "total_duration_ms": round(
                (perf_counter() - started) * 1000,
                2,
            )
        }
    )

@router.post("/query", response_model=QueryResponse)
async def query_endpoint(
    request: GenerateSQLRequest,
    response: Response,
) -> QueryResponse:
    request_id = uuid4()
    started = perf_counter()

    async def record_event(
        *,
        http_status: int,
        result: QueryResponse | None = None,
        error_code: str | None = None,
    ) -> dict[str, str]:
        saved = await asyncio.to_thread(
            write_audit_event,
            request_id=request_id,
            endpoint="/query",
            question=request.question,
            generated_sql=result.sql if result is not None else None,
            status="success" if result is not None else "failure",
            http_status=http_status,
            cache_hit=result.cache_hit if result is not None else None,
            executed=result.executed if result is not None else None,
            repair_count=(
                result.repair_count if result is not None else None
            ),
            row_count=result.row_count if result is not None else None,
            total_duration_ms=round(
                (perf_counter() - started) * 1000,
                2,
            ),
            database_duration_ms=(
                result.database_duration_ms
                if result is not None
                else None
            ),
            schema_version=(
                result.schema_version if result is not None else None
            ),
            model=settings.ollama_model,
            error_code=error_code,
        )

        return {
            "X-Request-ID": str(request_id),
            "X-Audit-Status": "saved" if saved else "failed",
        }

    try:
        result = await execute_query_request(request)
        result = result.model_copy(
            update={
                "explanation": summarize_result(
                    columns=result.columns,
                    rows=result.rows,
                    cache_hit=result.cache_hit,
                )
            }
        )

    except HTTPException as exc:
        audit_headers = await record_event(
            http_status=exc.status_code,
            error_code=f"HTTP_{exc.status_code}",
        )

        exc.headers = {
            **(exc.headers or {}),
            **audit_headers,
        }
        raise

    except Exception as exc:
        logger.error(
            "Unhandled query failure; request_id=%s; exception=%s",
            request_id,
            type(exc).__name__,
        )

        audit_headers = await record_event(
            http_status=500,
            error_code="INTERNAL_ERROR",
        )

        raise HTTPException(
            status_code=500,
            detail="Internal query error",
            headers=audit_headers,
        ) from None

    audit_headers = await record_event(
        http_status=200,
        result=result,
    )

    response.headers.update(audit_headers)

    return result.model_copy(
        update={
            "total_duration_ms": round(
                (perf_counter() - started) * 1000,
                2,
            )
        }
    )