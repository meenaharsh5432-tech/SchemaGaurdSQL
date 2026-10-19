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
        "public.products",
        "public.order_items",
        "public.support_tickets",
        "public.ticket_messages",
    }


def test_discovers_customer_columns_and_primary_key(discovered_tables):
    customers = discovered_tables["public.customers"]

    assert customers["primary_key"] == ["id"]
    assert [column["name"] for column in customers["columns"]] == [
        "id",
        "name",
        "city",
    ]


@pytest.mark.parametrize(
    "source,column,target",
    [
        ("orders", "customer_id", "customers"),
        ("order_items", "order_id", "orders"),
        ("order_items", "product_id", "products"),
        ("support_tickets", "customer_id", "customers"),
        ("ticket_messages", "ticket_id", "support_tickets"),
    ],
)
def test_discovers_relationships(
    discovered_tables, source, column, target
):
    assert {
        "columns": [column],
        "referenced_table": f"public.{target}",
        "referenced_columns": ["id"],
    } in discovered_tables[f"public.{source}"]["foreign_keys"]


def test_preserves_amount_description(discovered_tables):
    orders = discovered_tables["public.orders"]

    amount = next(
        column
        for column in orders["columns"]
        if column["name"] == "amount"
    )

    assert amount["nullable"] is False
    assert amount["description"] == (
        "Authoritative total order amount in INR. "
        "Sum this column for overall order revenue. "
        "Joining line items can repeat this amount; "
        "do not sum repeated order totals."
    )


def test_preserves_historical_price_description(discovered_tables):
    items = discovered_tables["public.order_items"]

    unit_price = next(
        column
        for column in items["columns"]
        if column["name"] == "unit_price"
    )

    assert unit_price["nullable"] is False
    assert unit_price["description"] == (
        "Historical sale price per unit in INR. "
        "Line value is quantity multiplied by unit_price."
    )