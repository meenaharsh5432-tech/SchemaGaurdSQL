import math

import httpx

from app.config import settings


EMBEDDING_MODEL = "embeddinggemma:300m"


class EmbeddingError(ValueError):
    """The embedding service returned invalid vectors."""


def embed_texts(texts: list[str]) -> list[tuple[float, ...]]:
    if not texts:
        return []

    if any(not text.strip() for text in texts):
        raise EmbeddingError("Embedding input cannot be blank")

    with httpx.Client(
        base_url=settings.ollama_base_url,
        timeout=httpx.Timeout(120.0, connect=5.0),
        trust_env=False,
    ) as client:
        response = client.post(
            "/api/embed",
            json={
                "model": EMBEDDING_MODEL,
                "input": texts,
                "truncate": False,
            },
        )
        response.raise_for_status()
        data = response.json()

    vectors = data.get("embeddings") if isinstance(data, dict) else None

    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise EmbeddingError("Unexpected embedding count")

    normalized = []
    dimensions = None

    for vector in vectors:
        if not isinstance(vector, list) or not vector:
            raise EmbeddingError("Embedding must be a nonempty list")

        if dimensions is None:
            dimensions = len(vector)
        elif len(vector) != dimensions:
            raise EmbeddingError("Embedding dimensions do not match")

        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            for value in vector
        ):
            raise EmbeddingError("Embedding contains nonnumeric values")

        values = tuple(float(value) for value in vector)

        if not all(math.isfinite(value) for value in values):
            raise EmbeddingError("Embedding contains nonfinite values")

        magnitude = math.hypot(*values)

        if magnitude == 0 or not math.isfinite(magnitude):
            raise EmbeddingError("Embedding has invalid magnitude")

        normalized.append(
            tuple(value / magnitude for value in values)
        )

    return normalized


def cosine_similarity(
    left: tuple[float, ...],
    right: tuple[float, ...],
) -> float:
    """Inputs must be unit vectors returned by embed_texts."""
    if len(left) != len(right):
        raise EmbeddingError("Cannot compare different vector dimensions")

    return sum(a * b for a, b in zip(left, right))