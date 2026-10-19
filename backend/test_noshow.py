import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import database
from app.ai import noshow
from app.main import app
import seed_data
import seed_noshow_demo

NOW = datetime(2026, 10, 18, 10, 0)


def snapshot(path: Path, signal: bool) -> None:
    """Build a demo database once; every test works on its own copy."""
    old = database.DATABASE_PATH
    database.DATABASE_PATH = path
    try:
        database.initialize_database()
        with database.get_connection() as connection:
            seed_data.build(connection, days=70, now=NOW)
            if signal:
                seed_noshow_demo.build(connection, now=NOW)
    finally:
        database.DATABASE_PATH = old


class NoShowTestCase(unittest.TestCase):
    signal = True
    _base_dir = None

    @classmethod
    def setUpClass(cls):
        cls._base_dir = tempfile.TemporaryDirectory()
        cls.base = Path(cls._base_dir.name) / "base.db"
        snapshot(cls.base, cls.signal)

    @classmethod
    def tearDownClass(cls):
        cls._base_dir.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = database.DATABASE_PATH, noshow.now, noshow.OUTBOX_PATH
        database.DATABASE_PATH = Path(self.temp.name) / "noshow.db"
        shutil.copy(self.base, database.DATABASE_PATH)
        noshow.now = lambda: NOW
        noshow.OUTBOX_PATH = Path(self.temp.name) / "outbox.jsonl"

    def tearDown(self):
        database.DATABASE_PATH, noshow.now, noshow.OUTBOX_PATH = self.old
        self.temp.cleanup()

    def reservations(self):
        with database.get_connection() as c:
            return [tuple(r) for r in c.execute(
                "SELECT id, user_id, table_id, party_size, reserved_for, status FROM reservations ORDER BY id")]


class SignalTests(NoShowTestCase):
    def test_signal_is_learned_and_validated_chronologically(self):
        report = noshow.overview(7, NOW)
        self.assertEqual(report["model"], "LogisticRegression")
        self.assertLess(report["model_brier"], report["baseline_brier"])
        self.assertGreater(report["model_auc"], 0.6)
        # The riskiest quarter of the holdout really misses more often than the rest.
        self.assertGreater(report["top_quartile_rate"], report["other_rate"])
        self.assertLessEqual(report["training_to"], NOW.date().isoformat())
        self.assertGreater(report["holdout_size"], 0)

    def test_predictions_cover_only_upcoming_confirmed_reservations(self):
        report = noshow.overview(3, NOW)
        end = (NOW + timedelta(days=4)).strftime("%Y-%m-%d")
        self.assertTrue(report["predictions"])
        with database.get_connection() as c:
            statuses = {r["id"]: r["status"] for r in c.execute("SELECT id, status FROM reservations")}
        for item in report["predictions"]:
            self.assertEqual(statuses[item["id"]], "booked")
            self.assertGreaterEqual(item["reserved_for"], NOW.strftime("%Y-%m-%d %H:%M:%S"))
            self.assertLess(item["reserved_for"], end)
            self.assertTrue(0 < item["probability"] < 1)
            self.assertIn(item["risk"], ("low", "medium", "high"))
            self.assertLessEqual(len(item["factors"]), 3)
            self.assertNotIn("_row", item)
            self.assertNotIn("@", json.dumps(item))   # no contact details in the report
        riskiest = max(report["predictions"], key=lambda item: item["probability"])
        self.assertTrue(riskiest["factors"])

    def test_services_and_overbooking_are_consistent(self):
        report = noshow.overview(7, NOW)
        self.assertTrue(report["services"])
        for service in report["services"]:
            self.assertIn(service["service"], ("lunch", "dinner"))
            self.assertLessEqual(service["suggested_extra_bookings"], noshow.OVERBOOK_MAX)
            self.assertLessEqual(service["suggested_extra_bookings"], service["expected_no_shows"])
            if service["suggested_extra_bookings"]:
                self.assertLessEqual(service["clash_risk"], noshow.OVERBOOK_TOLERANCE)
        self.assertEqual(sum(s["bookings"] for s in report["services"]), len(report["predictions"]))

    def test_reminders_are_targeted_and_never_duplicated(self):
        report = noshow.overview(7, NOW)
        risk = {p["id"]: p["risk"] for p in report["predictions"]}
        first = noshow.schedule_reminders(7, NOW)
        self.assertGreater(first["planned"], 0)
        self.assertEqual(first["created"], first["planned"])
        second = noshow.schedule_reminders(7, NOW)
        self.assertEqual((second["created"], second["already_scheduled"]), (0, second["planned"]))
        stored = noshow.list_reminders(200)
        self.assertEqual(len(stored), first["planned"])
        for reminder in stored:
            self.assertIn(risk[reminder["reservation_id"]], ("medium", "high"))
            self.assertEqual(reminder["status"], "pending")
            self.assertLess(reminder["scheduled_for"], reminder["reserved_for"])
        # Same-day reminders are for high risk only, and only one per reservation and kind.
        for item in noshow.overview(7, NOW)["reminder_plan"]:
            self.assertTrue(item["already_scheduled"])
            if item["kind"] == "same_day":
                self.assertEqual(risk[item["reservation_id"]], "high")

    def test_dispatch_skips_changed_reservations_and_never_repeats(self):
        noshow.schedule_reminders(7, NOW)
        pending = noshow.list_reminders(200)
        victim = pending[0]["reservation_id"]
        with database.get_connection() as c:
            c.execute("UPDATE reservations SET status='cancelled' WHERE id=?", (victim,))
        sent = []
        later = NOW + timedelta(days=9)   # everything is due, but some bookings are then in the past
        result = noshow.dispatch_reminders(later, sent.append)
        self.assertEqual(result["dispatched"], len(sent))
        self.assertEqual(result["failed"], 0)
        self.assertNotIn(victim, {entry["reservation_id"] for entry in sent})
        self.assertGreater(result["skipped"], 0)
        again = noshow.dispatch_reminders(later, sent.append)
        self.assertEqual((again["dispatched"], again["skipped"]), (0, 0))
        statuses = {r["id"]: r for r in noshow.list_reminders(200)}
        self.assertEqual(sum(r["status"] == "pending" for r in statuses.values()), 0)
        cancelled = [r for r in statuses.values() if r["reservation_id"] == victim]
        self.assertTrue(all(r["status"] == "skipped" for r in cancelled))

    def test_dispatch_on_time_uses_outbox_file_and_keeps_failures_pending(self):
        noshow.schedule_reminders(7, NOW)
        due = [r for r in noshow.list_reminders(200) if r["scheduled_for"] <= NOW.strftime("%Y-%m-%d %H:%M:%S")]
        self.assertTrue(due, "a booking within 24 hours should have produced an immediate reminder")
        with patch("app.ai.noshow.OUTBOX_PATH", Path(self.temp.name) / "missing" / "outbox.jsonl"), \
                patch("pathlib.Path.open", side_effect=OSError("disk full")):
            failed = noshow.dispatch_reminders(NOW)
        self.assertGreater(failed["failed"], 0)
        self.assertEqual(failed["dispatched"], 0)
        self.assertTrue(any(r["status"] == "pending" and "retry" in (r["detail"] or "") for r in noshow.list_reminders(200)))
        result = noshow.dispatch_reminders(NOW)
        self.assertGreater(result["dispatched"], 0)
        lines = noshow.OUTBOX_PATH.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), result["dispatched"])
        entry = json.loads(lines[0])
        self.assertIn(entry["channel"], ("sms", "email"))
        self.assertTrue(entry["to"])
        self.assertTrue(entry["message"].startswith("Hello "))

    def test_messages_do_not_expose_the_prediction(self):
        for step in noshow.overview(7, NOW)["reminder_plan"]:
            lowered = step["message"].lower()
            self.assertNotIn("no-show", lowered)
            self.assertNotIn("%", step["message"])
            self.assertIn("cancel", lowered)
            self.assertIn(noshow.RESTAURANT_NAME, step["message"])

    def test_reservations_are_never_modified_by_the_module(self):
        before = self.reservations()
        noshow.overview(7, NOW)
        noshow.schedule_reminders(7, NOW)
        noshow.dispatch_reminders(NOW + timedelta(days=9), lambda entry: None)
        self.assertEqual(self.reservations(), before)

    def test_api_access_and_flow(self):
        with TestClient(app) as client:
            for method, path in (("get", "/api/ai/noshow/overview"), ("post", "/api/ai/noshow/reminders/schedule"),
                                 ("post", "/api/ai/noshow/reminders/dispatch"), ("get", "/api/ai/noshow/reminders")):
                self.assertEqual(getattr(client, method)(path).status_code, 401, path)
            client.post("/api/auth/login", json={"email": "demo@nirvana.test", "password": "nirvana-demo"})
            self.assertEqual(client.get("/api/ai/noshow/overview").status_code, 403)
            self.assertEqual(client.post("/api/ai/noshow/reminders/schedule").status_code, 403)
            client.post("/api/auth/logout")
            client.post("/api/auth/login", json={"email": "manager@nirvana.test", "password": "nirvana-demo"})
            self.assertEqual(client.get("/api/ai/noshow/overview", params={"days": 0}).status_code, 422)
            self.assertEqual(client.get("/api/ai/noshow/overview", params={"days": 15}).status_code, 422)
            overview = client.get("/api/ai/noshow/overview", params={"days": 7})
            self.assertEqual(overview.status_code, 200)
            body = overview.json()
            self.assertEqual(body["horizon_days"], 7)
            self.assertEqual(body["model"], "LogisticRegression")
            scheduled = client.post("/api/ai/noshow/reminders/schedule", params={"days": 7}).json()
            self.assertEqual(scheduled["created"], len(body["reminder_plan"]))
            dispatched = client.post("/api/ai/noshow/reminders/dispatch").json()
            self.assertEqual(dispatched["failed"], 0)
            self.assertEqual(dispatched["delivery"], "outbox")
            listed = client.get("/api/ai/noshow/reminders").json()
            self.assertEqual(len(listed), scheduled["created"])


class NoSignalTests(NoShowTestCase):
    signal = False

    def test_baseline_is_used_honestly_when_outcomes_are_random(self):
        report = noshow.overview(7, NOW)
        self.assertEqual(report["model"], "base-rate-baseline")
        self.assertIn("did not beat", report["notice"])
        self.assertTrue(report["predictions"])
        self.assertEqual({p["risk"] for p in report["predictions"]}, {"average"})
        self.assertEqual(len({p["probability"] for p in report["predictions"]}), 1)
        self.assertFalse(any(p["factors"] for p in report["predictions"]))
        # Nobody can be singled out, so no reminder is planned or stored.
        self.assertEqual(report["reminder_plan"], [])
        self.assertEqual(noshow.schedule_reminders(7, NOW)["created"], 0)
        self.assertEqual(noshow.list_reminders(), [])


class PureFunctionTests(unittest.TestCase):
    def test_no_show_distribution(self):
        self.assertEqual(noshow.no_show_distribution([]), [1.0])
        self.assertEqual(noshow.no_show_distribution([0.5, 0.5]), [0.25, 0.5, 0.25])
        distribution = noshow.no_show_distribution([0.1, 0.2, 0.3, 0.4, 0.05])
        self.assertAlmostEqual(sum(distribution), 1.0)
        mean = sum(k * mass for k, mass in enumerate(distribution))
        self.assertAlmostEqual(mean, 1.05)

    def test_overbooking_is_conservative_and_bounded(self):
        self.assertEqual(noshow.suggest_overbooking([])["suggested_extra_bookings"], 0)
        self.assertEqual(noshow.suggest_overbooking([0.05] * 6)["suggested_extra_bookings"], 0)
        busy = noshow.suggest_overbooking([0.3] * 20)
        self.assertEqual(busy["suggested_extra_bookings"], noshow.OVERBOOK_MAX)
        self.assertLessEqual(busy["clash_risk"], noshow.OVERBOOK_TOLERANCE)
        with patch("app.ai.noshow.OVERBOOK_MAX", 10):
            wide = noshow.suggest_overbooking([0.3] * 20)
        self.assertGreaterEqual(wide["suggested_extra_bookings"], busy["suggested_extra_bookings"])
        self.assertLessEqual(wide["suggested_extra_bookings"], int(wide["expected_no_shows"]))
        self.assertLessEqual(wide["clash_risk"], noshow.OVERBOOK_TOLERANCE)
        with patch("app.ai.noshow.OVERBOOK_TOLERANCE", 0.01):
            strict = noshow.suggest_overbooking([0.3] * 20)
        self.assertLessEqual(strict["suggested_extra_bookings"], busy["suggested_extra_bookings"])

    def test_features_use_only_earlier_reservations(self):
        with tempfile.TemporaryDirectory() as folder:
            old = database.DATABASE_PATH
            database.DATABASE_PATH = Path(folder) / "history.db"
            try:
                database.initialize_database()
                with database.get_connection() as c:
                    c.execute("INSERT INTO users (email, full_name, password_hash) VALUES ('a@example.com', 'Ana Test', 'x')")
                    day = lambda n, hour=19: (NOW.replace(hour=hour) + timedelta(days=n)).strftime("%Y-%m-%d %H:%M:%S")
                    c.executemany(
                        "INSERT INTO reservations (user_id, party_size, reserved_for, status, created_at) VALUES (1, 2, ?, ?, ?)",
                        [(day(-10), "completed", day(-12)), (day(-9), "no_show", day(-11)), (day(-8), "cancelled", day(-10)),
                         (day(-7), "no_show", day(-9)), (day(2), "booked", day(-1)), (day(3), "booked", day(-1))])
                    rows = noshow.load_rows(c, NOW)
            finally:
                database.DATABASE_PATH = old
        # (resolved, no_shows, all past, cancelled) known strictly before each reservation
        self.assertEqual([r["history"] for r in rows],
                         [(0, 0, 0, 0), (1, 0, 1, 0), (2, 1, 2, 0), (2, 1, 3, 1), (3, 2, 4, 1), (3, 2, 4, 1)])
        first, last = noshow.vector(rows[0], 0.1, 0.1), noshow.vector(rows[-1], 0.1, 0.1)
        self.assertEqual(len(first), len(noshow.FEATURES))
        self.assertEqual(first[noshow.FEATURES.index("new_customer")], 1)
        self.assertEqual(last[noshow.FEATURES.index("new_customer")], 0)
        self.assertGreater(last[noshow.FEATURES.index("history_no_show_rate")], first[noshow.FEATURES.index("history_no_show_rate")])

    def test_too_little_history_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            old = database.DATABASE_PATH
            database.DATABASE_PATH = Path(folder) / "empty.db"
            try:
                database.initialize_database()
                with self.assertRaises(HTTPException) as error:
                    noshow.overview(7, NOW)
                self.assertEqual(error.exception.status_code, 422)
                with TestClient(app) as client:
                    import create_user
                    create_user.save_user("staff@example.com", "Staff", "staff", "staff-password")
                    client.post("/api/auth/login", json={"email": "staff@example.com", "password": "staff-password"})
                    self.assertEqual(client.get("/api/ai/noshow/overview").status_code, 422)
            finally:
                database.DATABASE_PATH = old

    def test_demo_seed_can_be_removed_without_touching_other_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            old = database.DATABASE_PATH
            database.DATABASE_PATH = Path(folder) / "demo.db"
            try:
                database.initialize_database()
                with database.get_connection() as c:
                    seed_data.build(c, days=30, now=NOW)
                    before = c.execute("SELECT COUNT(*) FROM reservations").fetchone()[0]
                    self.assertEqual(seed_noshow_demo.demo_rows(c), 0)
                    added = seed_noshow_demo.build(c, now=NOW)["added"]
                    self.assertEqual(seed_noshow_demo.demo_rows(c), added)
                    c.execute("DELETE FROM reservations WHERE table_id IS NULL")
                    self.assertEqual(c.execute("SELECT COUNT(*) FROM reservations").fetchone()[0], before)
            finally:
                database.DATABASE_PATH = old


if __name__ == "__main__":
    unittest.main()
