import json

from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.cache.redis_cache import (
    build_cache_key,
    get_cached_payload,
    set_cached_payload,
)
from app.config import settings
from app.guardrails.sql_validator import (
    ALLOWED_TABLES,
    SQLValidationError,
    validate_sql,
)
from app.schemas.query import QueryResponse


# Increment when prompts, generation settings, or query policy change.
POLICY_VERSION = "query-policy-v3-existence-example"


def query_cache_key(question: str, schema_version: str) -> str:
    url = make_url(settings.database_url.get_secret_value())

    # Include database identity without credentials.
    database_identity = json.dumps(
        {
            "driver": url.drivername,
            "host": url.host,
            "port": url.port,
            "database": url.database,
        },
        sort_keys=True,
    )

    # Trusted server-side scope for our current single-role application.
    authorization_scope = json.dumps(
        {
            "role": url.username,
            "tables": sorted(
                f"public.{table}" for table in ALLOWED_TABLES
            ),
        },
        sort_keys=True,
    )

    return build_cache_key(
        question=question,
        database_identity=database_identity,
        authorization_scope=authorization_scope,
        schema_version=schema_version,
        model=settings.ollama_model,
        policy_version=(
    f"{POLICY_VERSION}:"
    f"{'retrieval-v1' if settings.schema_retrieval_enabled else 'full-schema'}"
),
    )


def read_query_cache(
    question: str,
    schema_version: str,
) -> QueryResponse | None:
    key = query_cache_key(question, schema_version)
    payload = get_cached_payload(key)

    if payload is None:
        return None

    try:
        cached = QueryResponse.model_validate_json(payload)

        if (
            cached.question != question
            or cached.schema_version != schema_version
            or cached.model != settings.ollama_model
            or cached.cache_hit
            or not cached.executed
            or cached.row_count != len(cached.rows)
            or any(
                len(row) != len(cached.columns)
                for row in cached.rows
            )
        ):
            return None

        # Recheck stored SQL against the current application policy.
        if validate_sql(cached.sql) != cached.sql:
            return None

    except (ValidationError, SQLValidationError):
        return None

    return cached


def write_query_cache(response: QueryResponse) -> bool:
    if response.cache_hit or not response.executed:
        return False

    key = query_cache_key(
        response.question,
        response.schema_version,
    )

    return set_cached_payload(key, response.model_dump_json())