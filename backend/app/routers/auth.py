import os
import sqlite3
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status  # type: ignore

from app.auth import current_user, end_session, public_user, start_session
from app.database import get_connection
from app.schemas import LoginRequest, RegisterRequest, User
from app.security import hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

INVALID_LOGIN = "Incorrect email or password"
# Verified when the email is unknown so both failures take the same time.
_DUMMY_HASH = hash_password("timing-equaliser")

# Brute-force protection: after MAX_FAILED_LOGINS wrong passwords for one email
# within LOCK_MINUTES, that email is blocked until the window passes. Kept in
# memory, which is enough for a single server process.
MAX_FAILED_LOGINS = int(os.getenv("LOGIN_MAX_FAILURES", "5"))
LOCK_MINUTES = int(os.getenv("LOGIN_LOCK_MINUTES", "15"))
_failures: dict[str, list[float]] = {}
_failures_lock = threading.Lock()


def _recent_failures(email: str, now: float) -> list[float]:
    recent = [t for t in _failures.get(email, []) if now - t < LOCK_MINUTES * 60]
    _failures[email] = recent
    return recent


def reset_login_limits() -> None:
    with _failures_lock:
        _failures.clear()


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, response: Response):
    email, full_name = body.email.lower(), body.full_name
    try:
        with get_connection() as connection:
            user_id = connection.execute(
                "INSERT INTO users (email, full_name, password_hash, role) VALUES (?, ?, ?, 'customer')",
                (email, full_name, hash_password(body.password))).lastrowid
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    start_session(response, user_id)
    return public_user(row)


@router.post("/login", response_model=User)
def login(body: LoginRequest, response: Response):
    email = body.email.strip().lower()
    with _failures_lock:
        failures = _recent_failures(email, time.time())
        if len(failures) >= MAX_FAILED_LOGINS:
            wait = max(1, round((LOCK_MINUTES * 60 - (time.time() - failures[0])) / 60))
            raise HTTPException(status_code=429, detail=f"Too many failed sign-in attempts. Try again in {wait} minute"
                                                        f"{'s' if wait > 1 else ''}")
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    valid = verify_password(body.password, row["password_hash"] if row else _DUMMY_HASH) and row is not None
    with _failures_lock:
        if not valid:
            _failures.setdefault(email, []).append(time.time())
        else:
            _failures.pop(email, None)
    if not valid:
        raise HTTPException(status_code=401, detail=INVALID_LOGIN)
    start_session(response, row["id"])
    return public_user(row)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response):
    end_session(request, response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=User)
def me(user: dict = Depends(current_user)):
    return user
