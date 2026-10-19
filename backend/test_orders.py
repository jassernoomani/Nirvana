import tempfile
import threading
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal environments
    from starlette.testclient import TestClient  # type: ignore[import-not-found]

from app import database
from app.main import app
from create_user import save_user

PIZZA, TEA, RETIRED = 1, 2, 3


class OrderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = database.DATABASE_PATH
        database.DATABASE_PATH = Path(self.temp.name) / "orders.db"
        database.initialize_database()
        with database.get_connection() as connection:
            connection.executemany(
                "INSERT INTO menu_items (id, name, price, category, is_available) VALUES (?, ?, ?, ?, ?)",
                [(PIZZA, "Pizza", 10.0, "Pizza", 1), (TEA, "Tea", 3.0, "Drinks", 1), (RETIRED, "Old dish", 8.0, "Mains", 0)])
            connection.executemany("INSERT INTO ingredients (id, name, unit, stock_quantity) VALUES (?, ?, ?, ?)",
                                   [(1, "Dough", "g", 1000), (2, "Tea leaves", "g", 100), (3, "Rice", "g", 500)])
            # One pizza uses 200 g of dough, so 1000 g makes exactly 5.
            connection.executemany("INSERT INTO dish_ingredients VALUES (?, ?, ?)",
                                   [(PIZZA, 1, 200), (TEA, 2, 5), (RETIRED, 3, 100)])
        save_user("ana@example.com", "Ana", "customer", "ana-password")
        save_user("ben@example.com", "Ben", "customer", "ben-password")
        save_user("staff@example.com", "Staff", "staff", "staff-password")
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.sign_in("ana@example.com", "ana-password")

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        database.DATABASE_PATH = self.original
        self.temp.cleanup()

    def sign_in(self, email, password, client=None):
        client = client or self.client
        client.cookies.clear()
        self.assertEqual(client.post("/api/auth/login", json={"email": email, "password": password}).status_code, 200)

    def checkout(self, items, key="checkout-key-1", client=None):
        return (client or self.client).post("/api/orders", json={
            "items": [{"menu_item_id": d, "quantity": q} for d, q in items], "idempotency_key": key})

    def scalar(self, sql, parameters=()):
        with database.get_connection() as connection:
            return connection.execute(sql, parameters).fetchone()[0]

    def stock(self, ingredient_id):
        return self.scalar("SELECT stock_quantity FROM ingredients WHERE id = ?", (ingredient_id,))

    def test_checkout_creates_order_with_server_prices_and_updates_stock(self):
        response = self.checkout([(PIZZA, 2), (TEA, 3)])
        self.assertEqual(response.status_code, 201)
        order = response.json()
        self.assertRegex(order["reference"], r"^NV-[2-9A-HJ-NP-Z]{8}$")
        self.assertEqual(order["status"], "pending")
        self.assertEqual(order["total"], 29.0)
        self.assertEqual({(i["name"], i["quantity"], i["unit_price"], i["line_total"]) for i in order["items"]},
                         {("Pizza", 2, 10.0, 20.0), ("Tea", 3, 3.0, 9.0)})
        self.assertEqual((self.stock(1), self.stock(2)), (600, 85))
        self.assertEqual(self.scalar("SELECT user_id FROM orders WHERE reference = ?", (order["reference"],)),
                         self.scalar("SELECT id FROM users WHERE email = 'ana@example.com'"))
        self.assertEqual(self.client.get(f"/api/orders/{order['reference']}").json(), order)

    def test_client_prices_and_totals_are_rejected(self):
        for body in [
            {"items": [{"menu_item_id": PIZZA, "quantity": 1, "unit_price": 0.01}], "idempotency_key": "checkout-key-1"},
            {"items": [{"menu_item_id": PIZZA, "quantity": 1}], "total": 0.01, "idempotency_key": "checkout-key-1"},
        ]:
            self.assertEqual(self.client.post("/api/orders", json=body).status_code, 422)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM orders"), 0)

    def test_invalid_carts(self):
        empty = self.checkout([])
        self.assertEqual((empty.status_code, empty.json()["detail"]), (422, "Your cart is empty"))
        for quantity in [0, -1, 100]:
            self.assertEqual(self.checkout([(PIZZA, quantity)]).status_code, 422, quantity)
        self.assertEqual(self.checkout([(TEA, 60), (TEA, 40)]).status_code, 422)
        missing = self.checkout([(PIZZA, 1), (999, 1)])
        self.assertEqual(missing.status_code, 422)
        self.assertIn("999", missing.json()["detail"])
        unavailable = self.checkout([(PIZZA, 1), (RETIRED, 1)])
        self.assertEqual(unavailable.status_code, 409)
        self.assertIn("Old dish", unavailable.json()["detail"])
        self.assertEqual(self.client.post("/api/orders", json={"items": [{"menu_item_id": PIZZA, "quantity": 1}],
                                                               "idempotency_key": "x"}).status_code, 422)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM orders"), 0)
        self.assertEqual(self.stock(1), 1000)

    def test_overselling_is_refused(self):
        too_many = self.checkout([(PIZZA, 6), (TEA, 1)], key="checkout-key-1")
        self.assertEqual(too_many.status_code, 409)
        self.assertIn("Pizza (we can prepare 5 more)", too_many.json()["detail"])
        self.assertEqual((self.stock(1), self.stock(2)), (1000, 100))
        self.assertEqual(self.checkout([(PIZZA, 5)], key="checkout-key-2").status_code, 201)
        self.assertEqual(self.stock(1), 0)
        sold_out = self.checkout([(PIZZA, 1)], key="checkout-key-3")
        self.assertEqual(sold_out.status_code, 409)
        self.assertIn("Pizza (sold out for now)", sold_out.json()["detail"])

    def test_concurrent_checkouts_never_oversell(self):
        results = []

        def buy(index):
            with TestClient(app) as client:
                self.sign_in("ben@example.com", "ben-password", client)
                results.append(self.checkout([(PIZZA, 1)], key=f"parallel-key-{index}", client=client).status_code)

        threads = [threading.Thread(target=buy, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [201] * 5 + [409] * 3)
        self.assertEqual(self.stock(1), 0)

    def test_repeated_submission_returns_the_same_order(self):
        first = self.checkout([(PIZZA, 1)], key="same-key-123")
        again = self.checkout([(PIZZA, 1)], key="same-key-123")
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(first.json()["reference"], again.json()["reference"])
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM orders"), 1)
        self.assertEqual(self.stock(1), 800)
        self.assertEqual(self.checkout([(PIZZA, 1)], key="other-key-123").status_code, 201)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM orders"), 2)

    def test_order_keeps_the_original_price(self):
        reference = self.checkout([(PIZZA, 1)]).json()["reference"]
        self.sign_in("staff@example.com", "staff-password")
        self.assertEqual(self.client.patch(f"/api/menu/{PIZZA}", json={"price": 15}).status_code, 200)
        self.sign_in("ana@example.com", "ana-password")
        order = self.client.get(f"/api/orders/{reference}").json()
        self.assertEqual((order["total"], order["items"][0]["unit_price"]), (10.0, 10.0))

    def test_order_history_is_paged(self):
        # Regression for the review finding: only the 50 newest orders were reachable.
        with database.get_connection() as connection:
            ana = connection.execute("SELECT id FROM users WHERE email = 'ana@example.com'").fetchone()[0]
            for index in range(55):
                connection.execute(
                    "INSERT INTO orders (user_id, status, total, created_at, reference) VALUES (?, 'served', 3, ?, ?)",
                    (ana, f"2026-09-{1 + index // 2:02d} 12:{index % 2:02d}:00", f"NV-PAGE{index:04d}"))
        first = self.client.get("/api/orders", params={"limit": 20}).json()
        rest = self.client.get("/api/orders", params={"limit": 50, "offset": 20}).json()
        self.assertEqual((len(first), len(rest)), (20, 35))
        references = [o["reference"] for o in first + rest]
        self.assertEqual(len(set(references)), 55)
        self.assertEqual(references[0], "NV-PAGE0054")
        self.assertEqual(references[-1], "NV-PAGE0000")
        for params in [{"limit": 0}, {"limit": 101}, {"offset": -1}]:
            self.assertEqual(self.client.get("/api/orders", params=params).status_code, 422, params)

    def test_access_rules(self):
        reference = self.checkout([(TEA, 1)]).json()["reference"]
        self.assertEqual([o["reference"] for o in self.client.get("/api/orders").json()], [reference])

        self.sign_in("ben@example.com", "ben-password")
        self.assertEqual(self.client.get(f"/api/orders/{reference}").status_code, 404)
        self.assertEqual(self.client.get("/api/orders").json(), [])

        self.sign_in("staff@example.com", "staff-password")
        self.assertEqual(self.checkout([(TEA, 1)], key="staff-key-123").status_code, 403)
        self.assertEqual(self.client.get(f"/api/orders/{reference}").status_code, 200)

        self.client.cookies.clear()
        self.assertEqual(self.checkout([(TEA, 1)], key="anon-key-123").status_code, 401)
        self.assertEqual(self.client.get("/api/orders").status_code, 401)


if __name__ == "__main__":
    unittest.main()
