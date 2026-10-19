from unittest.mock import Mock

import pytest

from app.retrieval import schema_cache as cache_module


@pytest.fixture
def cache_setup(monkeypatch):
    clock = [100.0]

    loader = Mock(
        return_value={
            "dialect": "postgres",
            "tables": [{"table": "public.customers"}],
        }
    )

    monkeypatch.setattr(
        cache_module,
        "monotonic",
        lambda: clock[0],
    )
    monkeypatch.setattr(cache_module, "load_schema", loader)

    cache = cache_module.SchemaCache(ttl_seconds=60)

    return cache, loader, clock


def test_reuses_snapshot_before_expiry(cache_setup):
    cache, loader, clock = cache_setup

    first = cache.get()
    clock[0] += 59
    second = cache.get()

    assert second is first
    assert loader.call_count == 1


def test_refreshes_at_expiry(cache_setup):
    cache, loader, clock = cache_setup

    first = cache.get()
    clock[0] += 60
    second = cache.get()

    assert loader.call_count == 2
    assert second is not first
    assert second.version == first.version


def test_changed_metadata_changes_version(cache_setup):
    cache, loader, clock = cache_setup

    first = cache.get()

    loader.return_value = {
        "dialect": "postgres",
        "tables": [
            {
                "table": "public.customers",
                "description": "Updated customer description",
            }
        ],
    }

    clock[0] += 60
    second = cache.get()

    assert second.version != first.version


def test_invalidation_forces_refresh(cache_setup):
    cache, loader, _ = cache_setup

    cache.get()
    cache.invalidate()
    cache.get()

    assert loader.call_count == 2


def test_refresh_failure_does_not_serve_expired_snapshot(cache_setup):
    cache, loader, clock = cache_setup

    cache.get()
    clock[0] += 60
    loader.side_effect = RuntimeError("Database unavailable")

    with pytest.raises(RuntimeError, match="Database unavailable"):
        cache.get()

    # A failed refresh must not extend the cache lifetime.
    with pytest.raises(RuntimeError, match="Database unavailable"):
        cache.get()

    assert loader.call_count == 3