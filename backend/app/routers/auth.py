import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status  # type: ignore

from app.auth import current_user, end_session, public_user, start_session
from app.database import get_connection
from app.schemas import LoginRequest, RegisterRequest, User
from app.security import hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

INVALID_LOGIN = "Incorrect email or password"
# Verified when the email is unknown so both failures take the same time.
_DUMMY_HASH = hash_password("timing-equaliser")


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
    with get_connection() as connection:
        row = connection.execute("SELECT * FROM users WHERE email = ?", (body.email.strip(),)).fetchone()
    if row is None:
        verify_password(body.password, _DUMMY_HASH)
        raise HTTPException(status_code=401, detail=INVALID_LOGIN)
    if not verify_password(body.password, row["password_hash"]):
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
