"""Create a customer or staff account, or reset an existing account's password.

Run from backend. The password is asked for at the prompt so it never appears in
source code or shell history:

    .venv/Scripts/python.exe create_user.py --email chef@example.com --name "Head Chef" --role staff

This is the only way to create a staff account besides the demo seed; public
registration always creates customers.
"""
import argparse
import getpass
import sqlite3
import sys

from app import database
from app.security import hash_password


def save_user(email: str, full_name: str, role: str, password: str, update: bool = False) -> str:
    if role not in ("customer", "staff"):
        raise ValueError("role must be customer or staff")
    if not 8 <= len(password) <= 128:
        raise ValueError("password must be 8 to 128 characters")
    database.initialize_database()
    with database.get_connection() as connection:
        existing = connection.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing and not update:
            raise ValueError(f"{email} already exists; pass --update to change its role and password")
        if existing:
            connection.execute("UPDATE users SET full_name = ?, role = ?, password_hash = ? WHERE id = ?",
                               (full_name, role, hash_password(password), existing["id"]))
            # Changing the password signs the account out everywhere.
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (existing["id"],))
            return "updated"
        connection.execute("INSERT INTO users (email, full_name, password_hash, role) VALUES (?, ?, ?, ?)",
                           (email, full_name, hash_password(password), role))
        return "created"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True, help="full name shown in the app")
    parser.add_argument("--role", choices=["customer", "staff"], default="customer")
    parser.add_argument("--update", action="store_true", help="update the account if the email already exists")
    args = parser.parse_args()

    password = getpass.getpass("Password (8 to 128 characters): ")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    try:
        outcome = save_user(args.email.strip().lower(), args.name.strip(), args.role, password, args.update)
    except (ValueError, sqlite3.Error) as error:
        sys.exit(f"Error: {error}")
    print(f"{args.role.capitalize()} account {args.email} {outcome}.")


if __name__ == "__main__":
    main()
