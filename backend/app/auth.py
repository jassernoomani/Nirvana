"""Cookie-based sessions and role checks.

The browser receives a random token in an HttpOnly cookie; only its SHA-256 hash
is stored, so a leaked database does not expose usable sessions. Every protected
route checks the session and role on the server, whatever the frontend shows.
"""
import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response, status  # type: ignore

from app.database import TIME_FORMAT, get_connection

SESSION_COOKIE = "nirvana_session"
SESSION_HOURS = int(os.getenv("SESSION_HOURS", "8"))
# Keep false for http://localhost; set COOKIE_SECURE=true when served over HTTPS.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


def public_user(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "email": row["email"], "full_name": row["full_name"], "role": row["role"],
            "is_vegetarian": bool(row["is_vegetarian"])}


def start_session(response: Response, user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    now = _now()
    with get_connection() as connection:
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now.strftime(TIME_FORMAT),))
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_hash(token), user_id, now.strftime(TIME_FORMAT),
             (now + timedelta(hours=SESSION_HOURS)).strftime(TIME_FORMAT)))
    response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_HOURS * 3600, httponly=True,
                        samesite="lax", secure=COOKIE_SECURE, path="/")


def end_session(request: Request, response: Response) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with get_connection() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(token),))
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax", secure=COOKIE_SECURE)


def current_user(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in to continue")
    with get_connection() as connection:
        row = connection.execute(
            "SELECT s.expires_at, u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
            (_hash(token),)).fetchone()
        expired = row is not None and row["expires_at"] <= _now().strftime(TIME_FORMAT)
        if expired:
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash(token),))
    # Raised outside the block so the expired session's deletion is committed.
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session is no longer valid. Please sign in again")
    if expired:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Please sign in again")
    return public_user(row)


def require_staff(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "staff":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This action is reserved for restaurant staff")
    return user


def require_customer(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "customer":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This action is reserved for customer accounts")
    return user
