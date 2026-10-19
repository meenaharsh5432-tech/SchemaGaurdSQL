from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging
from contextlib import asynccontextmanager
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.api.query import router as query_router
from app.audit.logger import audit_engine
from app.database import engine

logger=logging.getLogger(__name__)



@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        audit_engine.dispose()
        engine.dispose()

app = FastAPI(
    title="SchemaGuard SQL",
    description="Private text-to-SQL analyst API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(query_router)

class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str

class DatabaseReadinessResponse(BaseModel):
    status: Literal["ready"]
    database: Literal["connected"]
    database_user: str
    read_only: bool

@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="schemaguard-sql",
    )

@app.get("/ready",response_model=DatabaseReadinessResponse,tags=["health"],)
def readiness()->DatabaseReadinessResponse:
    try:
        with engine.connect() as connection:
            result=connection.execute(
                text(
                    """
                    SELECT
                        current_user AS database_user,
                        current_setting('transaction_read_only') AS read_only,
                        has_table_privilege(
                            current_user, 'public.customers', 'SELECT'
                        ) AND has_table_privilege(
                            current_user, 'public.orders', 'SELECT'
                        ) AS can_read,
                        has_table_privilege(
                            current_user, 'public.customers', 'UPDATE'
                        ) OR has_table_privilege(
                            current_user, 'public.orders', 'UPDATE'
                        ) AS can_update,
                        has_database_privilege(
                            current_user, current_database(), 'TEMP'
                        ) AS can_create_temp
                    """
                )
            ).mappings().one()
    except SQLAlchemyError as exc:
        logger.error(
            "Database readiness check failed (%s)",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from None

    restrictions_ok=(
        result["database_user"]=="sg_reader"
        and result["read_only"]=="on"
        and result["can_read"] and not result["can_update"] and not result["can_create_temp"]
    )

    if not restrictions_ok:
        raise HTTPException(
             status_code=503,
            detail="Database role configuration check failed",
        )

    return DatabaseReadinessResponse(
        status="ready",
        database="connected",
        database_user=result["database_user"],
        read_only=True,
    )