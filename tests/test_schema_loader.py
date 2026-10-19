import pytest

from app.retrieval.schema_loader import load_schema


@pytest.fixture(scope="module")
def discovered_tables():
    schema = load_schema()

    assert schema["dialect"] == "postgres"

    return {
        table["table"]: table
        for table in schema["tables"]
    }


def test_discovers_only_allowed_tables(discovered_tables):
    assert set(discovered_tables) == {
        "public.customers",
        "public.orders",
    }


def test_discovers_customer_columns_and_primary_key(discovered_tables):
    customers = discovered_tables["public.customers"]

    assert customers["primary_key"] == ["id"]
    assert [column["name"] for column in customers["columns"]] == [
        "id",
        "name",
        "city",
    ]


def test_discovers_order_relationship(discovered_tables):
    orders = discovered_tables["public.orders"]

    assert {
        "columns": ["customer_id"],
        "referenced_table": "public.customers",
        "referenced_columns": ["id"],
    } in orders["foreign_keys"]


def test_preserves_amount_description(discovered_tables):
    orders = discovered_tables["public.orders"]

    amount = next(
        column
        for column in orders["columns"]
        if column["name"] == "amount"
    )

    assert amount["nullable"] is False
    assert amount["description"] == "Order amount in INR."