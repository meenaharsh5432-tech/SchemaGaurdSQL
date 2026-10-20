import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError


class SQLValidationError(ValueError):
    """SQL does not satisfy our supported query policy."""


ALLOWED_TABLES = {
    "customers",
    "orders",
    "products",
    "order_items",
    "support_tickets",
    "ticket_messages",
}
MAX_ROWS = 100

# Exact node types: unlisted SQL structures are rejected.
ALLOWED_NODES = {
    exp.Select,
    exp.From,
    exp.Table,
    exp.TableAlias,
    exp.Column,
    exp.Identifier,
    exp.Alias,
    exp.Star,
    exp.Join,
    exp.Where,
    exp.Group,
    exp.Having,
    exp.Order,
    exp.Ordered,
    exp.Limit,
    exp.Literal,
    exp.Boolean,
    exp.Null,
    exp.Paren,
    exp.Distinct,
    exp.And,
    exp.Or,
    exp.Not,
    exp.EQ,
    exp.NEQ,
    exp.GT,
    exp.GTE,
    exp.LT,
    exp.LTE,
    exp.Is,
    exp.Between,
    exp.In,
    exp.Like,
    exp.ILike,
    exp.Add,
    exp.Sub,
    exp.Mul,
    exp.Div,
    exp.Neg,
    exp.Sum,
    exp.Count,
    exp.Avg,
    exp.Min,
    exp.Max,
}


def identifier_name(identifier: exp.Identifier) -> str:
    # PostgreSQL folds unquoted identifiers to lowercase.
    if identifier.args.get("quoted"):
        return identifier.name
    return identifier.name.lower()


def validate_sql(
    sql: str,
    *,
    allowed_tables: frozenset[str] | None = None,
) -> str:
    permitted_tables = (
        ALLOWED_TABLES if allowed_tables is None else allowed_tables
    )
    if not sql.strip():
        raise SQLValidationError("SQL cannot be empty")

    if len(sql) > 10000:
        raise SQLValidationError("SQL exceeds the length limit")

    try:
        statements = sqlglot.parse(sql, read="postgres")
    except SqlglotError as exc:
        raise SQLValidationError("SQL could not be parsed") from exc

    if len(statements) != 1 or statements[0] is None:
        raise SQLValidationError("Exactly one statement is required")

    tree = statements[0]

    if type(tree) is not exp.Select:
        raise SQLValidationError("Only SELECT queries are supported")

    for node in tree.walk():
        if type(node) not in ALLOWED_NODES:
            raise SQLValidationError(
                f"Unsupported SQL structure: {type(node).__name__}"
            )

    tables = list(tree.find_all(exp.Table))

    if not tables:
        raise SQLValidationError("Query must read an allowed business table")

    for table in tables:
        if table.args.get("catalog") is not None:
            raise SQLValidationError("Catalog-qualified tables are forbidden")

        schema = table.args.get("db")
        name = table.this

        if not isinstance(schema, exp.Identifier):
            raise SQLValidationError("Use explicit public.table names")

        if identifier_name(schema) != "public":
            raise SQLValidationError("Only the public schema is allowed")

        if not isinstance(name, exp.Identifier):
            raise SQLValidationError("Only ordinary tables are supported")

        if identifier_name(name) not in permitted_tables:
            raise SQLValidationError("Table is not allowed")

    limit = tree.args.get("limit")

    if limit is None:
        tree = tree.limit(MAX_ROWS)
    else:
        value = limit.expression

        if (
            not isinstance(value, exp.Literal)
            or value.is_string
            or not value.this.isascii()
            or not value.this.isdigit()
        ):
            raise SQLValidationError("LIMIT must be a positive integer")

        requested_rows = int(value.this)

        if requested_rows < 1:
            raise SQLValidationError("LIMIT must be at least 1")

        tree = tree.limit(min(requested_rows, MAX_ROWS))

    # Return the checked, normalized query for later execution.
    return tree.sql(dialect="postgres")