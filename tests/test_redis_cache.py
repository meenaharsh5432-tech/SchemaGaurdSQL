from unittest.mock import Mock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.cache import redis_cache


BASE_CONTEXT = {
    "question": "List customer names",
    "database_identity": "local-schemaguard",
    "authorization_scope": "sg_reader:public.customers,public.orders",
    "schema_version": "schema-v1",
    "model": "qwen2.5-coder:3b",
    "policy_version": "policy-v1",
}


def test_key_is_stable():
    assert redis_cache.build_cache_key(
        **BASE_CONTEXT
    ) == redis_cache.build_cache_key(**BASE_CONTEXT)


@pytest.mark.parametrize("field", list(BASE_CONTEXT))
def test_context_changes_produce_different_keys(field):
    changed = dict(BASE_CONTEXT)
    changed[field] += "-changed"

    assert redis_cache.build_cache_key(
        **changed
    ) != redis_cache.build_cache_key(**BASE_CONTEXT)


def test_read_failure_is_cache_miss(monkeypatch):
    client = Mock()
    client.get.side_effect = RedisConnectionError("Unavailable")
    monkeypatch.setattr(redis_cache, "redis_client", client)

    assert redis_cache.get_cached_payload("test-key") is None


def test_write_includes_expiry(monkeypatch):
    client = Mock()
    client.set.return_value = True
    monkeypatch.setattr(redis_cache, "redis_client", client)

    assert redis_cache.set_cached_payload("test-key", '{"rows": []}')

    client.set.assert_called_once_with(
        "test-key",
        '{"rows": []}',
        ex=redis_cache.settings.result_cache_ttl_seconds,
    )


def test_write_failure_does_not_raise(monkeypatch):
    client = Mock()
    client.set.side_effect = RedisConnectionError("Unavailable")
    monkeypatch.setattr(redis_cache, "redis_client", client)

    assert redis_cache.set_cached_payload("test-key", "{}") is False