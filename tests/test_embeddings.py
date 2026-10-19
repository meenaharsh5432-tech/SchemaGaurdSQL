from unittest.mock import MagicMock

import httpx
import pytest

from app.retrieval import embeddings


@pytest.fixture
def mock_response(monkeypatch):
    response = MagicMock()
    client = MagicMock()
    client.post.return_value = response

    client_factory = MagicMock()
    client_factory.return_value.__enter__.return_value = client
    monkeypatch.setattr(embeddings.httpx, "Client", client_factory)

    return response, client


def test_normalizes_vectors(mock_response):
    response, client = mock_response
    response.json.return_value = {
        "embeddings": [[3.0, 4.0], [0.0, 2.0]]
    }

    vectors = embeddings.embed_texts(["sales", "support"])

    assert vectors[0] == pytest.approx((0.6, 0.8))
    assert vectors[1] == pytest.approx((0.0, 1.0))
    assert embeddings.cosine_similarity(
        vectors[0], vectors[0]
    ) == pytest.approx(1.0)

    payload = client.post.call_args.kwargs["json"]
    assert payload["input"] == ["sales", "support"]
    assert payload["truncate"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"embeddings": []},
        {"embeddings": [[]]},
        {"embeddings": [[0.0, 0.0]]},
        {"embeddings": [[True, 1.0]]},
        {"embeddings": [["invalid", 1.0]]},
        {"embeddings": [[float("nan"), 1.0]]},
        {"embeddings": [[float("inf"), 1.0]]},
    ],
)
def test_rejects_invalid_vectors(mock_response, payload):
    response, _ = mock_response
    response.json.return_value = payload

    with pytest.raises(embeddings.EmbeddingError):
        embeddings.embed_texts(["question"])


def test_rejects_inconsistent_dimensions(mock_response):
    response, _ = mock_response
    response.json.return_value = {
        "embeddings": [[1.0, 0.0], [1.0]]
    }

    with pytest.raises(
        embeddings.EmbeddingError, match="dimensions"
    ):
        embeddings.embed_texts(["sales", "support"])


def test_propagates_http_failure(mock_response):
    response, _ = mock_response
    request = httpx.Request(
        "POST", "http://localhost:11434/api/embed"
    )
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Unavailable",
        request=request,
        response=httpx.Response(503, request=request),
    )

    with pytest.raises(httpx.HTTPStatusError):
        embeddings.embed_texts(["question"])


def test_empty_and_blank_inputs_do_not_call_service(mock_response):
    _, client = mock_response

    assert embeddings.embed_texts([]) == []

    with pytest.raises(embeddings.EmbeddingError):
        embeddings.embed_texts([" "])

    client.post.assert_not_called()


def test_similarity_rejects_dimension_mismatch():
    with pytest.raises(embeddings.EmbeddingError):
        embeddings.cosine_similarity((1.0,), (1.0, 0.0))