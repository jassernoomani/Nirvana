import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal environments
    from starlette.testclient import TestClient  # type: ignore[import-not-found]

from app import auth, database
from app.main import app
from create_user import save_user

DISH = {"name": "Soup", "category": "Starters", "price": 5}


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = database.DATABASE_PATH
        database.DATABASE_PATH = Path(self.temp.name) / "auth.db"
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        save_user("staff@example.com", "Staff Member", "staff", "staff-password")
        save_user("customer@example.com", "Customer", "customer", "customer-password")

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        database.DATABASE_PATH = self.original
        self.temp.cleanup()

    def login(self, email, password):
        return self.client.post("/api/auth/login", json={"email": email, "password": password})

    def test_register_always_creates_a_signed_in_customer(self):
        response = self.client.post("/api/auth/register", json={
            "email": " New@Example.com ", "full_name": " New Person ", "password": "long-enough", "role": "staff"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["role"], "customer")
        self.assertEqual(response.json()["email"], "new@example.com")
        cookie = response.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertEqual(self.client.get("/api/auth/me").json()["full_name"], "New Person")
        self.assertEqual(self.client.post("/api/menu", json=DISH).status_code, 403)

    def test_register_validation(self):
        base = {"email": "x@example.com", "full_name": "X", "password": "long-enough"}
        for change in [{"password": "short"}, {"email": "not-an-email"}, {"full_name": "   "}]:
            self.assertEqual(self.client.post("/api/auth/register", json={**base, **change}).status_code, 422, change)
        duplicate = self.client.post("/api/auth/register", json={**base, "email": "CUSTOMER@example.com"})
        self.assertEqual(duplicate.status_code, 409)

    def test_login_failures_share_one_message(self):
        wrong_password = self.login("staff@example.com", "nope")
        unknown_email = self.login("nobody@example.com", "nope")
        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(unknown_email.status_code, 401)
        self.assertEqual(wrong_password.json(), unknown_email.json())
        self.assertNotIn("set-cookie", wrong_password.headers)

    def test_login_is_case_insensitive_and_me_returns_no_secrets(self):
        self.assertEqual(self.login("STAFF@example.com", "staff-password").status_code, 200)
        me = self.client.get("/api/auth/me").json()
        self.assertEqual(me["role"], "staff")
        self.assertNotIn("password_hash", me)

    def test_logout_ends_the_session_on_the_server(self):
        self.login("customer@example.com", "customer-password")
        token = self.client.cookies.get(auth.SESSION_COOKIE)
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        # Replaying the old cookie must not work either.
        self.client.cookies.set(auth.SESSION_COOKIE, token)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        with database.get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)

    def test_expired_session_is_rejected_and_removed(self):
        self.login("staff@example.com", "staff-password")
        with database.get_connection() as connection:
            connection.execute("UPDATE sessions SET expires_at = '2000-01-01 00:00:00'")
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)
        self.assertIn("expired", response.json()["detail"])
        with database.get_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 0)

    def test_forged_cookie_is_rejected(self):
        self.client.cookies.set(auth.SESSION_COOKIE, "made-up-token")
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.client.post("/api/menu", json=DISH).status_code, 401)

    def menu_changes(self, dish_id):
        return [self.client.put(f"/api/menu/{dish_id}", json=DISH).status_code,
                self.client.patch(f"/api/menu/{dish_id}", json={"price": 6}).status_code,
                self.client.delete(f"/api/menu/{dish_id}").status_code]

    def test_menu_changes_require_staff(self):
        self.login("staff@example.com", "staff-password")
        created = self.client.post("/api/menu", json=DISH)
        self.assertEqual(created.status_code, 201)
        dish_id = created.json()["id"]

        self.client.cookies.clear()
        self.assertEqual(self.client.post("/api/menu", json=DISH).status_code, 401)
        self.assertEqual(self.menu_changes(dish_id), [401, 401, 401])
        self.assertEqual(self.client.get("/api/menu").status_code, 200)

        self.login("customer@example.com", "customer-password")
        self.assertEqual(self.client.post("/api/menu", json=DISH).status_code, 403)
        self.assertEqual(self.menu_changes(dish_id), [403, 403, 403])
        self.assertEqual(self.client.get(f"/api/menu/{dish_id}").json()["price"], 5)

        self.client.cookies.clear()
        self.login("staff@example.com", "staff-password")
        self.assertEqual(self.menu_changes(dish_id), [200, 200, 204])

    def test_save_user_rules(self):
        with self.assertRaises(ValueError):
            save_user("customer@example.com", "Again", "customer", "another-password")
        with self.assertRaises(ValueError):
            save_user("x@example.com", "X", "admin", "long-enough")
        with self.assertRaises(ValueError):
            save_user("x@example.com", "X", "customer", "short")
        self.login("customer@example.com", "customer-password")
        self.assertEqual(save_user("customer@example.com", "Promoted", "staff", "new-password", update=True), "updated")
        # Updating an account signs it out, and the new password works.
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.login("customer@example.com", "new-password").json()["role"], "staff")


if __name__ == "__main__":
    unittest.main()
