import json
from typing import Any

from sqlalchemy import inspect

from app.database import engine
from app.guardrails.sql_validator import ALLOWED_TABLES


SCHEMA_NAME = "public"


def load_schema() -> dict[str, Any]:
    tables = []

    with engine.begin() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        connection.exec_driver_sql("SET LOCAL statement_timeout = '5s'")
        connection.exec_driver_sql("SET LOCAL lock_timeout = '1s'")
        connection.exec_driver_sql("SET LOCAL search_path = pg_catalog")

        inspector = inspect(connection)

        for table_name in sorted(ALLOWED_TABLES):
            columns = inspector.get_columns(
                table_name,
                schema=SCHEMA_NAME,
            )

            primary_key = inspector.get_pk_constraint(
                table_name,
                schema=SCHEMA_NAME,
            )

            table_comment = inspector.get_table_comment(
                table_name,
                schema=SCHEMA_NAME,
            )

            foreign_keys = []

            for foreign_key in inspector.get_foreign_keys(
                table_name,
                schema=SCHEMA_NAME,
                postgresql_ignore_search_path=True,
            ):
                target_schema = (
                    foreign_key["referred_schema"] or SCHEMA_NAME
                )
                target_table = foreign_key["referred_table"]

                # Do not include relationships to unauthorized tables.
                if (
                    target_schema != SCHEMA_NAME
                    or target_table not in ALLOWED_TABLES
                ):
                    continue

                foreign_keys.append(
                    {
                        "columns": foreign_key["constrained_columns"],
                        "referenced_table": (
                            f"{target_schema}.{target_table}"
                        ),
                        "referenced_columns": (
                            foreign_key["referred_columns"]
                        ),
                    }
                )

            tables.append(
                {
                    "table": f"{SCHEMA_NAME}.{table_name}",
                    "description": table_comment.get("text"),
                    "columns": [
                        {
                            "name": column["name"],
                            "type": str(
                                column["type"].compile(
                                    dialect=connection.dialect
                                )
                            ),
                            "nullable": column["nullable"],
                            "description": column.get("comment"),
                        }
                        for column in columns
                    ],
                    "primary_key": primary_key["constrained_columns"],
                    "foreign_keys": foreign_keys,
                }
            )

    return {
        "dialect": "postgres",
        "tables": tables,
    }


def load_schema_prompt() -> str:
    return json.dumps(
        load_schema(),
        ensure_ascii=False,
        indent=2,
    )