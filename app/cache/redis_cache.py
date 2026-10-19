import hashlib
import json
import logging

from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

from app.config import settings


logger = logging.getLogger(__name__)

redis_client = Redis.from_url(
    settings.redis_url.get_secret_value(),
    decode_responses=True,
    socket_connect_timeout=0.5,
    socket_timeout=0.5,
    retry=Retry(NoBackoff(), 0),
    max_connections=10,
)


def build_cache_key(
    *,
    question: str,
    database_identity: str,
    authorization_scope: str,
    schema_version: str,
    model: str,
    policy_version: str,
) -> str:
    context = {
        "question": question,
        "database_identity": database_identity,
        "authorization_scope": authorization_scope,
        "schema_version": schema_version,
        "model": model,
        "policy_version": policy_version,
    }

    serialized = json.dumps(
        context,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"schemaguard:results:v1:{digest}"


def get_cached_payload(key: str) -> str | None:
    try:
        return redis_client.get(key)
    except RedisError:
        logger.warning("Redis read failed; treating request as a cache miss")
        return None


def set_cached_payload(key: str, payload: str) -> bool:
    try:
        return bool(
            redis_client.set(
                key,
                payload,
                ex=settings.result_cache_ttl_seconds,
            )
        )
    except RedisError:
        logger.warning("Redis write failed; result was not cached")
        return False