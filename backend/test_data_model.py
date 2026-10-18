import tempfile
import unittest
from datetime import datetime
from pathlib import Path

try:
    from fastapi.testclient import TestClient  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal environments
    from starlette.testclient import TestClient  # type: ignore[import-not-found]

import seed_data
from app import database
from app.main import app
from app.security import hash_password, verify_password

NOW = datetime(2026, 10, 18, 20, 30)


class SeededDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.original = database.DATABASE_PATH
        database.DATABASE_PATH = Path(cls.temp.name) / "seed.db"
        database.initialize_database()
        with database.get_connection() as connection:
            cls.summary = seed_data.build(connection, days=14, now=NOW)

    @classmethod
    def tearDownClass(cls):
        database.DATABASE_PATH = cls.original
        cls.temp.cleanup()

    def query(self, sql, parameters=()):
        with database.get_connection() as connection:
            return connection.execute(sql, parameters).fetchall()

    def test_summary_counts(self):
        self.assertEqual(self.summary["dishes"], len(seed_data.MENU))
        self.assertEqual(self.summary["customers"], 120)
        self.assertGreater(self.summary["orders"], 500)
        self.assertGreater(self.summary["reviews"], 0)

    def test_customers_never_order_their_allergens(self):
        rows = self.query("""
            SELECT COUNT(*) FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            JOIN dish_ingredients di ON di.menu_item_id = oi.menu_item_id
            JOIN ingredient_allergens ia ON ia.ingredient_id = di.ingredient_id
            JOIN user_allergies ua ON ua.user_id = o.user_id AND ua.allergen_id = ia.allergen_id""")
        self.assertEqual(rows[0][0], 0)

    def test_vegetarians_only_order_vegetarian_dishes(self):
        rows = self.query("""
            SELECT COUNT(*) FROM orders o
            JOIN users u ON u.id = o.user_id AND u.is_vegetarian = 1
            JOIN order_items oi ON oi.order_id = o.id
            JOIN menu_items m ON m.id = oi.menu_item_id AND m.is_vegetarian = 0""")
        self.assertEqual(rows[0][0], 0)

    def test_vegetarian_flag_matches_recipe(self):
        meat = ", ".join("?" * len(seed_data.MEAT_OR_FISH))
        rows = self.query(f"""
            SELECT m.name FROM menu_items m WHERE m.is_vegetarian = 1 AND EXISTS (
                SELECT 1 FROM dish_ingredients di JOIN ingredients i ON i.id = di.ingredient_id
                WHERE di.menu_item_id = m.id AND i.name IN ({meat}))""", tuple(seed_data.MEAT_OR_FISH))
        self.assertEqual(rows, [])

    def test_order_totals_match_items(self):
        rows = self.query("""
            SELECT COUNT(*) FROM orders o
            WHERE ABS(o.total - (SELECT SUM(quantity * unit_price) FROM order_items WHERE order_id = o.id)) > 0.001""")
        self.assertEqual(rows[0][0], 0)

    def test_every_dish_has_a_recipe_and_image(self):
        rows = self.query("""
            SELECT m.id FROM menu_items m
            WHERE NOT EXISTS (SELECT 1 FROM dish_ingredients WHERE menu_item_id = m.id) OR m.image_url IS NULL""")
        self.assertEqual(rows, [])

    def test_live_orders_and_stock(self):
        statuses = dict(self.query("SELECT status, COUNT(*) FROM orders WHERE status IN ('pending', 'preparing', 'ready') GROUP BY status"))
        self.assertEqual(statuses, {"pending": 2, "preparing": 2, "ready": 1})
        low = {row[0] for row in self.query("SELECT name FROM ingredients WHERE stock_quantity < reorder_level")}
        self.assertTrue(low and low <= seed_data.LOW_STOCK)

    def test_reservations_do_not_overlap_on_a_table(self):
        rows = self.query("""
            SELECT COUNT(*) FROM reservations a JOIN reservations b
            ON a.table_id = b.table_id AND a.id < b.id
            AND ABS(strftime('%s', a.reserved_for) - strftime('%s', b.reserved_for)) < 7200""")
        self.assertEqual(rows[0][0], 0)
        too_small = self.query("""
            SELECT COUNT(*) FROM reservations r JOIN restaurant_tables t ON t.id = r.table_id
            WHERE t.seats < r.party_size""")
        self.assertEqual(too_small[0][0], 0)
        future = self.query("SELECT status FROM reservations WHERE reserved_for > ?", (NOW.strftime(seed_data.TIME_FORMAT),))
        self.assertTrue(future and all(row[0] == "booked" for row in future))

    def test_demo_accounts(self):
        rows = self.query("SELECT email, role, password_hash FROM users WHERE email LIKE '%@nirvana.test' ORDER BY email")
        self.assertEqual([(r[0], r[1]) for r in rows], [
            ("demo@nirvana.test", "customer"), ("kitchen@nirvana.test", "staff"), ("manager@nirvana.test", "staff")])
        self.assertTrue(all(verify_password(seed_data.DEMO_PASSWORD, r[2]) for r in rows))

    def test_seed_is_reproducible(self):
        with tempfile.TemporaryDirectory() as other:
            original = database.DATABASE_PATH
            database.DATABASE_PATH = Path(other) / "again.db"
            try:
                database.initialize_database()
                with database.get_connection() as connection:
                    self.assertEqual(seed_data.build(connection, days=14, now=NOW), self.summary)
            finally:
                database.DATABASE_PATH = original

    def test_dish_with_order_history_cannot_be_deleted(self):
        with TestClient(app) as client:
            client.post("/api/auth/login", json={"email": "manager@nirvana.test", "password": seed_data.DEMO_PASSWORD})
            response = client.delete("/api/menu/1")
            self.assertEqual(response.status_code, 409)
            self.assertEqual(client.get("/api/menu/1").status_code, 200)


class PasswordTests(unittest.TestCase):
    def test_hash_and_verify(self):
        stored = hash_password("correct horse")
        self.assertTrue(verify_password("correct horse", stored))
        self.assertFalse(verify_password("wrong", stored))
        self.assertNotEqual(stored, hash_password("correct horse"))
        self.assertFalse(verify_password("anything", "not-a-hash"))


if __name__ == "__main__":
    unittest.main()
