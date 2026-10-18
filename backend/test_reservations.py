import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path

try:
    from fastapi.testclient import TestClient  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal environments
    from starlette.testclient import TestClient  # type: ignore[import-not-found]

from app import database
from app.main import app
from app.routers import reservations
from create_user import save_user

NOW = datetime(2026, 10, 18, 10, 0)
TOMORROW = "2026-10-19"


class ReservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = database.DATABASE_PATH, reservations.now
        database.DATABASE_PATH = Path(self.temp.name) / "reservations.db"
        reservations.now = lambda: NOW
        database.initialize_database()
        with database.get_connection() as connection:
            connection.executemany("INSERT INTO restaurant_tables (label, seats) VALUES (?, ?)", [("T1", 2), ("T2", 4)])
        for name in ["ana", "ben", "cy", "dee", "eve", "fay"]:
            save_user(f"{name}@example.com", name.title(), "customer", f"{name}-password")
        save_user("staff@example.com", "Staff", "staff", "staff-password")
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.sign_in("ana")

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        database.DATABASE_PATH, reservations.now = self.original
        self.temp.cleanup()

    def sign_in(self, name, client=None):
        client = client or self.client
        client.cookies.clear()
        response = client.post("/api/auth/login", json={"email": f"{name}@example.com", "password": f"{name}-password"})
        self.assertEqual(response.status_code, 200)

    def book(self, time="19:00", party_size=2, day=TOMORROW, client=None, **extra):
        return (client or self.client).post("/api/reservations", json={
            "date": day, "time": time, "party_size": party_size, **extra})

    def test_availability_is_public_and_respects_capacity(self):
        self.client.cookies.clear()
        response = self.client.get("/api/reservations/availability", params={"date": TOMORROW, "party_size": 2})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual((body["max_party_size"], body["duration_minutes"]), (4, 120))
        self.assertEqual([s["time"] for s in body["slots"]], ["12:00", "12:30", "13:00", "13:30", "14:00",
                                                                "19:00", "19:30", "20:00", "20:30", "21:00"])
        self.assertTrue(all(s["available"] for s in body["slots"]))
        large = self.client.get("/api/reservations/availability", params={"date": TOMORROW, "party_size": 5}).json()
        self.assertFalse(any(s["available"] for s in large["slots"]))
        # Today at 10:00, the 12:00 slot is far enough ahead; nothing earlier exists.
        today = self.client.get("/api/reservations/availability", params={"date": "2026-10-18", "party_size": 2}).json()
        self.assertTrue(today["slots"][0]["available"])

    def test_booking_is_confirmed_with_the_smallest_free_table(self):
        response = self.book(party_size=2, contact_phone=" +216 22 345 678 ", notes="Window seat please")
        self.assertEqual(response.status_code, 201)
        reservation = response.json()
        self.assertEqual((reservation["status"], reservation["table_label"], reservation["reserved_for"]),
                         ("booked", "T1", "2026-10-19 19:00:00"))
        self.assertEqual((reservation["contact_phone"], reservation["notes"]), ("+216 22 345 678", "Window seat please"))
        self.assertEqual(self.book(time="12:00", party_size=3).json()["table_label"], "T2")
        self.assertEqual(len(self.client.get("/api/reservations").json()), 2)

    def test_invalid_requests(self):
        cases = [
            ({"day": "2026-10-17"}, "future"),
            ({"time": "12:15"}, "seating times"),
            ({"party_size": 5}, "up to 4 guests"),
            ({"day": "2027-01-30"}, "60 days"),
        ]
        for change, message in cases:
            response = self.book(**change)
            self.assertEqual(response.status_code, 422, change)
            self.assertIn(message, response.json()["detail"])
        reservations.now = lambda: datetime(2026, 10, 18, 11, 30)
        self.assertIn("60 minutes", self.book(day="2026-10-18", time="12:00").json()["detail"])
        for change in [{"time": "25:00"}, {"party_size": 0}, {"party_size": -2}, {"contact_phone": "call me"},
                       {"status": "confirmed"}, {"notes": "x" * 301}, {"day": "not-a-date"}]:
            self.assertEqual(self.book(**change).status_code, 422, change)
        self.assertEqual(self.client.get("/api/reservations").json(), [])

    def test_conflicting_bookings_are_refused(self):
        self.assertEqual(self.book(time="19:00").json()["table_label"], "T1")
        self.sign_in("ben")
        self.assertEqual(self.book(time="19:00").json()["table_label"], "T2")
        self.sign_in("cy")
        full = self.book(time="19:00")
        self.assertEqual(full.status_code, 409)
        self.assertIn("No table for 2", full.json()["detail"])
        # A seating lasts two hours: 20:30 still overlaps, 21:00 does not.
        self.assertEqual(self.book(time="20:30").status_code, 409)
        self.assertEqual(self.book(time="21:00").status_code, 201)
        slots = {s["time"]: s["available"] for s in self.client.get(
            "/api/reservations/availability", params={"date": TOMORROW, "party_size": 2}).json()["slots"]}
        self.assertEqual((slots["19:00"], slots["20:30"], slots["12:00"]), (False, False, True))

    def test_customer_cannot_double_book_themselves(self):
        self.assertEqual(self.book(time="19:00").status_code, 201)
        clash = self.book(time="20:00")
        self.assertEqual(clash.status_code, 409)
        self.assertIn("already have a reservation", clash.json()["detail"])

    def test_cancelling_frees_the_table(self):
        first = self.book(time="19:00", party_size=4).json()
        self.sign_in("ben")
        self.assertEqual(self.book(time="19:00", party_size=4).status_code, 409)
        self.sign_in("ana")
        cancelled = self.client.post(f"/api/reservations/{first['id']}/cancel")
        self.assertEqual((cancelled.status_code, cancelled.json()["status"]), (200, "cancelled"))
        self.assertEqual(self.client.post(f"/api/reservations/{first['id']}/cancel").status_code, 409)
        self.sign_in("ben")
        self.assertEqual(self.book(time="19:00", party_size=4).status_code, 201)

    def test_customers_only_see_and_change_their_own(self):
        reservation_id = self.book().json()["id"]
        self.sign_in("ben")
        self.assertEqual(self.client.get("/api/reservations").json(), [])
        self.assertEqual(self.client.post(f"/api/reservations/{reservation_id}/cancel").status_code, 404)
        self.sign_in("staff")
        self.assertEqual(self.book().status_code, 403)
        self.client.cookies.clear()
        self.assertEqual(self.book().status_code, 401)
        self.assertEqual(self.client.get("/api/reservations").status_code, 401)
        self.sign_in("ana")
        self.assertEqual(self.client.get("/api/reservations").json()[0]["status"], "booked")

    def test_simultaneous_bookings_never_share_a_table(self):
        results = []

        def attempt(name):
            with TestClient(app) as client:
                self.sign_in(name, client)
                results.append(self.book(client=client).status_code)

        threads = [threading.Thread(target=attempt, args=(n,)) for n in ["ben", "cy", "dee", "eve", "fay"]]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(results), [201, 201, 409, 409, 409])


if __name__ == "__main__":
    unittest.main()
