import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

DATABASE_PATH = Path(__file__).with_name("restaurant.db")


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database() -> None:
    with get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                price REAL NOT NULL CHECK (price > 0),
                category TEXT NOT NULL,
                is_available INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(menu_items)")}
        for name, definition in {
            "image_url": "TEXT",
            "preparation_minutes": "INTEGER NOT NULL DEFAULT 15 CHECK (preparation_minutes BETWEEN 1 AND 240)",
            "is_vegetarian": "INTEGER NOT NULL DEFAULT 0 CHECK (is_vegetarian IN (0, 1))",
        }.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE menu_items ADD COLUMN {name} {definition}")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_menu_category ON menu_items(category)")
