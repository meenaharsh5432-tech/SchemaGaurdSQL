import getpass
import sqlite3
from pathlib import Path

import psycopg
from psycopg import sql


SOURCE = (
    Path(__file__).resolve().parent
    / "data/spider/database/poker_player/poker_player.sqlite"
)

TABLES = {
    "people": [
        "people_id",
        "nationality",
        "name",
        "birth_date",
        "height",
    ],
    "poker_player": [
        "poker_player_id",
        "people_id",
        "final_table_made",
        "best_finish",
        "money_rank",
        "earnings",
    ],
}


def read_source():
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)

    connection = sqlite3.connect(
        SOURCE.resolve().as_uri() + "?mode=ro",
        uri=True,
    )

    try:
        rows = {}

        for table, columns in TABLES.items():
            # Identifiers come only from the fixed definitions above.
            column_sql = ", ".join(f'"{column}"' for column in columns)
            rows[table] = connection.execute(
                f'SELECT {column_sql} FROM "{table}" '
                f'ORDER BY "{columns[0]}"'
            ).fetchall()

        return rows
    finally:
        connection.close()


def main():
    source_rows = read_source()

    if len(source_rows["people"]) != 7:
        raise ValueError("Expected 7 source people")

    if len(source_rows["poker_player"]) != 5:
        raise ValueError("Expected 5 source poker players")

    admin_password = getpass.getpass("PostgreSQL admin password: ")
    reader_password = getpass.getpass(
        "Choose a password for sg_spider_reader: "
    )
    confirmation = getpass.getpass("Confirm reader password: ")

    if not reader_password or reader_password != confirmation:
        raise ValueError("Reader passwords are empty or do not match")

    with psycopg.connect(
        host="127.0.0.1",
        port=5433,
        dbname="schemaguard_spider",
        user="sg_admin",
        password=admin_password,
        connect_timeout=5,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            if cursor.fetchone()[0] != "schemaguard_spider":
                raise RuntimeError("Unexpected destination database")

            cursor.execute("SET LOCAL statement_timeout = '10s'")
            cursor.execute("SET LOCAL lock_timeout = '2s'")

            cursor.execute("""
                SELECT tablename
                FROM pg_catalog.pg_tables
                WHERE schemaname = 'public'
            """)
            if cursor.fetchall():
                raise RuntimeError(
                    "Destination public schema is not empty; import stopped"
                )

            cursor.execute("""
                SELECT 1 FROM pg_catalog.pg_roles
                WHERE rolname = 'sg_spider_reader'
            """)
            if cursor.fetchone():
                raise RuntimeError(
                    "sg_spider_reader already exists; import stopped"
                )

            cursor.execute("""
                CREATE TABLE public.people (
                    people_id INTEGER PRIMARY KEY,
                    nationality TEXT,
                    name TEXT,
                    birth_date TEXT,
                    height DOUBLE PRECISION
                )
            """)

            cursor.execute("""
                CREATE TABLE public.poker_player (
                    poker_player_id INTEGER PRIMARY KEY,
                    people_id INTEGER REFERENCES public.people(people_id),
                    final_table_made DOUBLE PRECISION,
                    best_finish DOUBLE PRECISION,
                    money_rank DOUBLE PRECISION,
                    earnings DOUBLE PRECISION
                )
            """)

            for table, columns in TABLES.items():
                column_sql = sql.SQL(", ").join(
                    sql.Identifier(column) for column in columns
                )

                insert = sql.SQL(
                    "INSERT INTO public.{} ({}) VALUES ({})"
                ).format(
                    sql.Identifier(table),
                    column_sql,
                    sql.SQL(", ").join(
                        sql.Placeholder() for _ in columns
                    ),
                )
                cursor.executemany(insert, source_rows[table])

                select = sql.SQL(
                    "SELECT {} FROM public.{} ORDER BY {}"
                ).format(
                    column_sql,
                    sql.Identifier(table),
                    sql.Identifier(columns[0]),
                )
                cursor.execute(select)
                imported_rows = cursor.fetchall()

                if imported_rows != source_rows[table]:
                    raise RuntimeError(
                        f"Imported values differ from SQLite: {table}"
                    )

            cursor.execute("""
                REVOKE ALL ON DATABASE schemaguard_spider FROM PUBLIC
            """)
            cursor.execute("""
                REVOKE ALL ON SCHEMA public FROM PUBLIC
            """)
            cursor.execute("""
                REVOKE ALL ON TABLE
                    public.people, public.poker_player
                FROM PUBLIC
            """)

            cursor.execute(
                sql.SQL("""
                    CREATE ROLE sg_spider_reader
                    LOGIN PASSWORD {}
                    NOSUPERUSER NOCREATEDB NOCREATEROLE
                    NOREPLICATION NOBYPASSRLS
                """).format(sql.Literal(reader_password))
            )

            cursor.execute("""
                GRANT CONNECT ON DATABASE schemaguard_spider
                TO sg_spider_reader
            """)
            cursor.execute("""
                GRANT USAGE ON SCHEMA public TO sg_spider_reader
            """)
            cursor.execute("""
                GRANT SELECT ON TABLE public.people, public.poker_player
                TO sg_spider_reader
            """)

            cursor.execute("""
                ALTER ROLE sg_spider_reader
                IN DATABASE schemaguard_spider
                SET default_transaction_read_only = on
            """)
            cursor.execute("""
                ALTER ROLE sg_spider_reader
                IN DATABASE schemaguard_spider
                SET statement_timeout = '5s'
            """)
            cursor.execute("""
                ALTER ROLE sg_spider_reader
                IN DATABASE schemaguard_spider
                SET lock_timeout = '1s'
            """)

    # Printed only after the transaction commits successfully.
    print("Import committed.")
    print("people: 7 rows; poker_player: 5 rows.")
    print("All imported row values match the SQLite source.")
    print("Read-only role created: sg_spider_reader")


if __name__ == "__main__":
    main()