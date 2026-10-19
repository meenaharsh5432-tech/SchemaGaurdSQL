import hashlib
import json
from dataclasses import dataclass
from threading import Lock
from time import monotonic

from app.retrieval.schema_loader import load_schema


@dataclass(frozen=True)
class SchemaSnapshot:
    prompt: str
    version: str


class SchemaCache:
    def __init__(self, ttl_seconds: float = 60.0):
        if ttl_seconds <= 0:
            raise ValueError("Schema cache TTL must be positive")

        self._ttl_seconds = ttl_seconds
        self._snapshot: SchemaSnapshot | None = None
        self._expires_at = 0.0
        self._lock = Lock()

    def get(self) -> SchemaSnapshot:
        # One thread refreshes; other callers wait for that snapshot.
        with self._lock:
            if (
                self._snapshot is not None
                and monotonic() < self._expires_at
            ):
                return self._snapshot

            metadata = load_schema()

            # Stable key ordering produces repeatable fingerprints.
            canonical_json = json.dumps(
                metadata,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )

            version = hashlib.sha256(
                canonical_json.encode("utf-8")
            ).hexdigest()

            snapshot = SchemaSnapshot(
                prompt=json.dumps(
                    metadata,
                    sort_keys=True,
                    ensure_ascii=False,
                    indent=2,
                ),
                version=version,
            )

            # Publish only after discovery and serialization succeed.
            self._snapshot = snapshot
            self._expires_at = monotonic() + self._ttl_seconds

            return snapshot

    def invalidate(self) -> None:
        with self._lock:
            self._snapshot = None
            self._expires_at = 0.0


schema_cache = SchemaCache(ttl_seconds=60)