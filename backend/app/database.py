import sqlite3
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

DATABASE_PATH = Path(__file__).with_name("restaurant.db")

# Tables added after the original menu table. Every statement is idempotent so
# startup can run them against new and existing databases alike.
SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS allergens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        unit TEXT NOT NULL CHECK (unit IN ('g', 'ml', 'piece')),
        stock_quantity REAL NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
        reorder_level REAL NOT NULL DEFAULT 0 CHECK (reorder_level >= 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ingredient_allergens (
        ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
        allergen_id INTEGER NOT NULL REFERENCES allergens(id) ON DELETE CASCADE,
        PRIMARY KEY (ingredient_id, allergen_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dish_ingredients (
        menu_item_id INTEGER NOT NULL REFERENCES menu_items(id) ON DELETE CASCADE,
        ingredient_id INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE RESTRICT,
        quantity REAL NOT NULL CHECK (quantity > 0),
        PRIMARY KEY (menu_item_id, ingredient_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL UNIQUE COLLATE NOCASE,
        full_name TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'staff')),
        is_vegetarian INTEGER NOT NULL DEFAULT 0 CHECK (is_vegetarian IN (0, 1)),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_allergies (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        allergen_id INTEGER NOT NULL REFERENCES allergens(id) ON DELETE CASCADE,
        PRIMARY KEY (user_id, allergen_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_favorite_categories (
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        category TEXT NOT NULL,
        PRIMARY KEY (user_id, category)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS restaurant_tables (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        label TEXT NOT NULL UNIQUE,
        seats INTEGER NOT NULL CHECK (seats > 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        table_id INTEGER REFERENCES restaurant_tables(id) ON DELETE SET NULL,
        party_size INTEGER NOT NULL CHECK (party_size BETWEEN 1 AND 20),
        reserved_for TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'booked'
            CHECK (status IN ('booked', 'seated', 'completed', 'cancelled', 'no_show')),
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'preparing', 'ready', 'served', 'cancelled')),
        total REAL NOT NULL CHECK (total >= 0),
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT,
        reference TEXT,
        idempotency_key TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS order_items (
        order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        menu_item_id INTEGER NOT NULL REFERENCES menu_items(id) ON DELETE RESTRICT,
        quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 99),
        unit_price REAL NOT NULL CHECK (unit_price > 0),
        PRIMARY KEY (order_id, menu_item_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        order_id INTEGER REFERENCES orders(id) ON DELETE SET NULL,
        rating INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
        comment TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_order_items_dish ON order_items(menu_item_id)",
    "CREATE INDEX IF NOT EXISTS idx_reservations_time ON reservations(reserved_for)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_created ON reviews(created_at)",
]


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
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
        for statement in SCHEMA:
            connection.execute(statement)
        # Columns added to orders after the first data-model release.
        order_columns = {row["name"] for row in connection.execute("PRAGMA table_info(orders)")}
        for name in ("reference", "idempotency_key"):
            if name not in order_columns:
                connection.execute(f"ALTER TABLE orders ADD COLUMN {name} TEXT")
        connection.execute("UPDATE orders SET reference = 'NV-' || upper(hex(randomblob(4))) WHERE reference IS NULL")
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_reference ON orders(reference)")
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_idempotency ON orders(user_id, idempotency_key)")
        reservation_columns = {row["name"] for row in connection.execute("PRAGMA table_info(reservations)")}
        if "contact_phone" not in reservation_columns:
            connection.execute("ALTER TABLE reservations ADD COLUMN contact_phone TEXT")
