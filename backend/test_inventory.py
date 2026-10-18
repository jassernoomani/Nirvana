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

DOUGH, LEMONS, BASIL = 1, 2, 3


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = database.DATABASE_PATH
        database.DATABASE_PATH = Path(self.temp.name) / "inventory.db"
        database.initialize_database()
        with database.get_connection() as connection:
            connection.executemany(
                "INSERT INTO ingredients (id, name, unit, stock_quantity, reorder_level) VALUES (?, ?, ?, ?, ?)",
                [(DOUGH, "Dough", "g", 1000, 300), (LEMONS, "Lemons", "piece", 2, 5), (BASIL, "Basil", "g", 0, 10)])
            connection.execute("INSERT INTO menu_items (id, name, price, category) VALUES (1, 'Pizza', 10, 'Pizza')")
            connection.execute("INSERT INTO dish_ingredients VALUES (1, ?, 200)", (DOUGH,))
        save_user("staff@example.com", "Sam Staff", "staff", "staff-password")
        save_user("ana@example.com", "Ana", "customer", "ana-password")
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.sign_in("staff@example.com", "staff-password")

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        database.DATABASE_PATH = self.original
        self.temp.cleanup()

    def sign_in(self, email, password, client=None):
        client = client or self.client
        client.cookies.clear()
        self.assertEqual(client.post("/api/auth/login", json={"email": email, "password": password}).status_code, 200)

    def adjust(self, ingredient_id, change, reason, client=None, **extra):
        return (client or self.client).post(f"/api/inventory/{ingredient_id}/adjust",
                                            json={"change": change, "reason": reason, **extra})

    def stock(self, ingredient_id):
        with database.get_connection() as connection:
            return connection.execute("SELECT stock_quantity FROM ingredients WHERE id = ?", (ingredient_id,)).fetchone()[0]

    def history(self, ingredient_id):
        return self.client.get(f"/api/inventory/{ingredient_id}/movements").json()

    def test_inventory_is_staff_only(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/api/inventory").status_code, 401)
        self.sign_in("ana@example.com", "ana-password")
        self.assertEqual(self.client.get("/api/inventory").status_code, 403)
        self.assertEqual(self.adjust(DOUGH, 100, "delivery").status_code, 403)
        self.assertEqual(self.client.put(f"/api/inventory/{DOUGH}", json={"stock_quantity": 0}).status_code, 403)
        self.assertEqual(self.client.get(f"/api/inventory/{DOUGH}/movements").status_code, 403)
        self.assertEqual(self.stock(DOUGH), 1000)

    def test_list_shows_status_and_usage(self):
        items = {i["name"]: i for i in self.client.get("/api/inventory").json()}
        self.assertEqual({name: i["status"] for name, i in items.items()}, {"Dough": "ok", "Lemons": "low", "Basil": "out"})
        self.assertEqual(items["Dough"]["used_in"], ["Pizza"])
        self.assertEqual((items["Lemons"]["stock_quantity"], items["Lemons"]["reorder_level"], items["Lemons"]["unit"]),
                         (2, 5, "piece"))

    def test_delivery_and_corrections_are_recorded(self):
        delivered = self.adjust(DOUGH, 500, "delivery", note="Weekly order")
        self.assertEqual((delivered.status_code, delivered.json()["stock_quantity"]), (200, 1500))
        self.assertEqual(self.adjust(DOUGH, -200, "waste").json()["stock_quantity"], 1300)
        self.assertEqual(self.adjust(LEMONS, 4, "correction").json()["status"], "ok")
        movements = self.history(DOUGH)
        self.assertEqual([(m["change"], m["quantity_after"], m["reason"], m["staff_name"]) for m in movements],
                         [(-200, 1300, "waste", "Sam Staff"), (500, 1500, "delivery", "Sam Staff")])
        self.assertEqual(movements[1]["note"], "Weekly order")
        self.assertTrue(movements[0]["created_at"])

    def test_stock_never_goes_negative(self):
        refused = self.adjust(DOUGH, -1000.5, "correction")
        self.assertEqual(refused.status_code, 409)
        self.assertIn("only 1000 g of Dough", refused.json()["detail"])
        self.assertEqual(self.stock(DOUGH), 1000)
        self.assertEqual(self.history(DOUGH), [])
        emptied = self.adjust(DOUGH, -1000, "correction").json()
        self.assertEqual((emptied["stock_quantity"], emptied["status"]), (0, "out"))

    def test_invalid_adjustments(self):
        for change, reason in [(-5, "delivery"), (5, "waste"), (0, "correction"), (5, "order"), (5, "gift")]:
            self.assertEqual(self.adjust(DOUGH, change, reason).status_code, 422, (change, reason))
        self.assertEqual(self.adjust(DOUGH, 5, "delivery", staff_id=99).status_code, 422)
        self.assertEqual(self.adjust(DOUGH, 2_000_000, "delivery").status_code, 422)
        self.assertEqual(self.adjust(999, 5, "delivery").status_code, 404)
        self.assertEqual(self.stock(DOUGH), 1000)

    def test_stocktake_and_minimum_level(self):
        counted = self.client.put(f"/api/inventory/{DOUGH}", json={"stock_quantity": 250, "note": "Monday count"})
        self.assertEqual((counted.status_code, counted.json()["status"]), (200, "low"))
        self.assertEqual([(m["change"], m["reason"], m["note"]) for m in self.history(DOUGH)], [(-750, "count", "Monday count")])
        relaxed = self.client.put(f"/api/inventory/{DOUGH}", json={"reorder_level": 200}).json()
        self.assertEqual((relaxed["reorder_level"], relaxed["status"]), (200, "ok"))
        self.assertEqual(len(self.history(DOUGH)), 1)
        for body in [{"stock_quantity": -1}, {"reorder_level": -5}, {}, {"stock_quantity": 5, "unit": "kg"}]:
            self.assertEqual(self.client.put(f"/api/inventory/{DOUGH}", json=body).status_code, 422, body)
        self.assertEqual(self.client.put("/api/inventory/999", json={"stock_quantity": 1}).status_code, 404)

    def test_orders_deduct_stock_and_appear_in_history(self):
        self.sign_in("ana@example.com", "ana-password")
        order = self.client.post("/api/orders", json={"items": [{"menu_item_id": 1, "quantity": 2}],
                                                      "idempotency_key": "inventory-test-1"}).json()
        self.sign_in("staff@example.com", "staff-password")
        self.assertEqual(self.stock(DOUGH), 600)
        movement = self.history(DOUGH)[0]
        self.assertEqual((movement["change"], movement["reason"], movement["order_reference"], movement["staff_name"]),
                         (-400, "order", order["reference"], None))

    def test_concurrent_orders_and_adjustments_stay_consistent(self):
        results = {"orders": [], "waste": []}

        def order(index):
            with TestClient(app) as client:
                self.sign_in("ana@example.com", "ana-password", client)
                results["orders"].append(client.post("/api/orders", json={
                    "items": [{"menu_item_id": 1, "quantity": 1}], "idempotency_key": f"race-key-{index}"}).status_code)

        def waste():
            with TestClient(app) as client:
                self.sign_in("staff@example.com", "staff-password", client)
                results["waste"].append(self.adjust(DOUGH, -500, "waste", client=client).status_code)

        threads = [threading.Thread(target=order, args=(i,)) for i in range(5)] + [threading.Thread(target=waste)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        sold = results["orders"].count(201)
        wasted = 500 if results["waste"] == [200] else 0
        self.assertGreaterEqual(self.stock(DOUGH), 0)
        self.assertEqual(self.stock(DOUGH), 1000 - 200 * sold - wasted)
        self.assertEqual(sum(m["change"] for m in self.history(DOUGH)), -(200 * sold + wasted))


if __name__ == "__main__":
    unittest.main()
