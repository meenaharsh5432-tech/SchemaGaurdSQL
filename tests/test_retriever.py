import json
import math

import pytest

from app.retrieval import retriever
from app.retrieval.schema_cache import SchemaSnapshot


def table(name, references=()):
    return {
        "table": f"public.{name}",
        "description": name,
        "columns": [],
        "primary_key": ["id"],
        "foreign_keys": [
            {
                "columns": [f"{target}_id"],
                "referenced_table": f"public.{target}",
                "referenced_columns": ["id"],
            }
            for target in references
        ],
    }


def snapshot(tables, version="v1"):
    return SchemaSnapshot(
        prompt=json.dumps({
            "dialect": "postgres",
            "tables": tables,
        }),
        version=version,
    )


def install_embeddings(monkeypatch, scores):
    calls = []

    def fake_embed(texts):
        calls.append(list(texts))

        # Table documents are JSON; questions are plain text.
        if texts[0].startswith("{"):
            vectors = []
            for text in texts:
                name = json.loads(text)["table"]
                score = scores[name]
                vectors.append(
                    (score, math.sqrt(max(0.0, 1 - score * score)))
                )
            return vectors

        return [(1.0, 0.0)]

    monkeypatch.setattr(retriever, "embed_texts", fake_embed)
    return calls


def test_excludes_low_scoring_unrelated_table(monkeypatch):
    install_embeddings(monkeypatch, {
        "public.support_tickets": 0.9,
        "public.ticket_messages": 0.7,
        "public.products": 0.2,
    })
    schema = snapshot([
        table("support_tickets"),
        table("ticket_messages", ["support_tickets"]),
        table("products"),
    ])

    result = retriever.SchemaRetriever().retrieve(
        "Which requests need attention?", schema
    )

    assert set(result.selected_tables) == {
        "public.support_tickets",
        "public.ticket_messages",
    }
    assert result.schema_version == "v1"


def test_explicit_mention_recovers_low_scoring_table(monkeypatch):
    install_embeddings(monkeypatch, {
        "public.customers": 0.1,
        "public.support_tickets": 0.9,
    })
    schema = snapshot([
        table("customers"),
        table("support_tickets", ["customers"]),
    ])

    result = retriever.SchemaRetriever().retrieve(
        "Show customer names for support tickets.",
        schema,
        top_k=1,
    )

    assert set(result.selected_tables) == {
        "public.customers",
        "public.support_tickets",
    }


def test_adds_intermediate_join_tables(monkeypatch):
    install_embeddings(monkeypatch, {
        "public.customers": 0.95,
        "public.orders": 0.1,
        "public.order_items": 0.1,
        "public.products": 0.9,
    })
    schema = snapshot([
        table("customers"),
        table("orders", ["customers"]),
        table("order_items", ["orders", "products"]),
        table("products"),
    ])

    result = retriever.SchemaRetriever().retrieve(
        "Show purchases.", schema, top_k=2
    )

    assert set(result.selected_tables) == {
        "public.customers",
        "public.orders",
        "public.order_items",
        "public.products",
    }


def test_omitted_tables_are_not_referenced_in_prompt(monkeypatch):
    install_embeddings(monkeypatch, {
        "public.customers": 0.1,
        "public.orders": 0.9,
    })
    schema = snapshot([
        table("customers"),
        table("orders", ["customers"]),
    ])

    result = retriever.SchemaRetriever().retrieve(
        "Show revenue.", schema, top_k=1
    )
    metadata = json.loads(result.prompt)

    assert result.selected_tables == ("public.orders",)
    assert metadata["tables"][0]["foreign_keys"] == []


def test_reuses_index_and_invalidates_on_schema_or_model_change(
    monkeypatch,
):
    calls = install_embeddings(monkeypatch, {
        "public.customers": 0.9,
    })
    instance = retriever.SchemaRetriever()
    tables = [table("customers")]

    instance.retrieve("First question", snapshot(tables))
    instance.retrieve("Second question", snapshot(tables))

    def document_calls():
        return sum(call[0].startswith("{") for call in calls)

    assert document_calls() == 1

    instance.retrieve("Third question", snapshot(tables, "v2"))
    assert document_calls() == 2

    monkeypatch.setattr(
        retriever, "EMBEDDING_MODEL", "different-test-model"
    )
    instance.retrieve("Fourth question", snapshot(tables, "v2"))
    assert document_calls() == 3


def test_failed_index_build_is_retried(monkeypatch):
    calls = install_embeddings(monkeypatch, {
        "public.customers": 0.9,
    })
    working_embed = retriever.embed_texts
    failed = False

    def fail_once(texts):
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("Embedding service unavailable")
        return working_embed(texts)

    monkeypatch.setattr(retriever, "embed_texts", fail_once)
    instance = retriever.SchemaRetriever()
    schema = snapshot([table("customers")])

    with pytest.raises(RuntimeError):
        instance.retrieve("Show people.", schema)

    result = instance.retrieve("Show people.", schema)

    assert result.selected_tables == ("public.customers",)
    assert sum(call[0].startswith("{") for call in calls) == 1


def test_nonpositive_scores_fall_back_to_full_schema(monkeypatch):
    install_embeddings(monkeypatch, {
        "public.customers": -0.2,
        "public.products": -0.3,
    })
    schema = snapshot([
        table("customers"),
        table("products"),
    ])

    result = retriever.SchemaRetriever().retrieve(
        "Unrelated question.", schema
    )

    assert set(result.selected_tables) == {
        "public.customers",
        "public.products",
    }