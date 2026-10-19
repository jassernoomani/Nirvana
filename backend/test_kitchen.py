import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal environments
    from starlette.testclient import TestClient  # type: ignore[import-not-found]

from app import database
from app.main import app
from create_user import save_user


class KitchenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = database.DATABASE_PATH
        database.DATABASE_PATH = Path(self.temp.name) / "kitchen.db"
        database.initialize_database()
        save_user("staff@example.com", "Sam Staff", "staff", "staff-password")
        save_user("ana@example.com", "Ana Lopez", "customer", "ana-password")
        with database.get_connection() as connection:
            connection.executemany("INSERT INTO menu_items (id, name, price, category, preparation_minutes) VALUES (?, ?, ?, ?, ?)",
                                   [(1, "Pizza", 10, "Pizza", 20), (2, "Tea", 3, "Drinks", 5)])
            ana = connection.execute("SELECT id FROM users WHERE email = 'ana@example.com'").fetchone()[0]
            # id, user, status, created_at
            for order_id, user, status, created in [
                    (1, ana, "pending", "2026-10-19 12:10:00"), (2, None, "pending", "2026-10-19 12:01:00"),
                    (3, ana, "preparing", "2026-10-19 11:50:00"), (4, ana, "ready", "2026-10-19 11:40:00"),
                    (5, ana, "served", "2026-10-19 11:00:00"), (6, ana, "cancelled", "2026-10-19 11:05:00")]:
                connection.execute("INSERT INTO orders (id, user_id, status, total, created_at, reference) VALUES (?, ?, ?, 13, ?, ?)",
                                   (order_id, user, status, created, f"NV-TEST000{order_id}"))
                connection.executemany("INSERT INTO order_items VALUES (?, ?, ?, ?)", [(order_id, 1, 1, 10), (order_id, 2, 1, 3)])
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.sign_in("staff@example.com", "staff-password")

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        database.DATABASE_PATH = self.original
        self.temp.cleanup()

    def sign_in(self, email, password):
        self.client.cookies.clear()
        self.assertEqual(self.client.post("/api/auth/login", json={"email": email, "password": password}).status_code, 200)

    def move(self, order_id, from_status, to_status):
        return self.client.post(f"/api/kitchen/orders/{order_id}/status", json={"from_status": from_status, "to_status": to_status})

    def test_board_lists_open_orders_oldest_first(self):
        orders = self.client.get("/api/kitchen/orders").json()
        self.assertEqual([(o["id"], o["status"]) for o in orders], [(4, "ready"), (3, "preparing"), (2, "pending"), (1, "pending")])
        first = orders[0]
        self.assertEqual((first["reference"], first["customer_name"], first["item_count"], first["longest_preparation_minutes"]),
                         ("NV-TEST0004", "Ana Lopez", 2, 20))
        self.assertEqual([(i["name"], i["quantity"]) for i in first["items"]], [("Pizza", 1), ("Tea", 1)])
        self.assertIsNone(orders[2]["customer_name"])
        self.assertEqual(first["status_since"], first["created_at"])

    def test_full_workflow_is_persisted(self):
        self.assertEqual(self.move(1, "pending", "preparing").json()["status"], "preparing")
        ready = self.move(1, "preparing", "ready").json()
        self.assertEqual(ready["status"], "ready")
        self.assertNotEqual(ready["status_since"], ready["created_at"])
        self.assertEqual(self.move(1, "ready", "served").status_code, 200)
        self.assertNotIn(1, [o["id"] for o in self.client.get("/api/kitchen/orders").json()])
        with database.get_connection() as connection:
            history = connection.execute(
                "SELECT h.from_status, h.to_status, u.full_name FROM order_status_history h JOIN users u ON u.id = h.staff_id "
                "WHERE order_id = 1 ORDER BY h.id").fetchall()
            completed = connection.execute("SELECT completed_at FROM orders WHERE id = 1").fetchone()[0]
        self.assertEqual([tuple(r) for r in history], [("pending", "preparing", "Sam Staff"),
                                                       ("preparing", "ready", "Sam Staff"), ("ready", "served", "Sam Staff")])
        self.assertIsNotNone(completed)
        # The customer sees the new status on their order page.
        self.sign_in("ana@example.com", "ana-password")
        self.assertEqual(self.client.get("/api/orders/NV-TEST0001").json()["status"], "served")

    def test_invalid_transitions_are_refused(self):
        for from_status, to_status in [("pending", "ready"), ("pending", "served"), ("ready", "preparing"),
                                       ("preparing", "pending"), ("pending", "pending")]:
            self.assertEqual(self.move(1, from_status, to_status).status_code, 422, (from_status, to_status))
        for body in [{"from_status": "pending", "to_status": "cancelled"}, {"to_status": "preparing"},
                     {"from_status": "pending", "to_status": "preparing", "note": "x"}]:
            self.assertEqual(self.client.post("/api/kitchen/orders/1/status", json=body).status_code, 422, body)
        # The stated current status must match the real one.
        stale = self.move(5, "pending", "preparing")
        self.assertEqual(stale.status_code, 409)
        self.assertIn("already served", stale.json()["detail"])
        self.assertEqual(self.move(6, "pending", "preparing").status_code, 409)
        self.assertEqual(self.move(999, "pending", "preparing").status_code, 404)

    def test_two_screens_cannot_advance_twice(self):
        self.assertEqual(self.move(2, "pending", "preparing").status_code, 200)
        self.assertEqual(self.move(2, "pending", "preparing").status_code, 409)
        with database.get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM order_status_history WHERE order_id = 2").fetchone()[0], 1)

    def test_kitchen_is_staff_only(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/kitchen/orders").status_code, 401)
        self.assertEqual(self.move(1, "pending", "preparing").status_code, 401)
        self.sign_in("ana@example.com", "ana-password")
        self.assertEqual(self.client.get("/api/kitchen/orders").status_code, 403)
        self.assertEqual(self.move(1, "pending", "preparing").status_code, 403)
        with database.get_connection() as connection:
            self.assertEqual(connection.execute("SELECT status FROM orders WHERE id = 1").fetchone()[0], "pending")


if __name__ == "__main__":
    unittest.main()
