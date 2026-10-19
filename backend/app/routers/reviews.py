import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status  # type: ignore

from app.ai.reviews import INJECTION, redact
from app.auth import require_customer
from app.database import get_connection, now_text
from app.routers.orders import load_orders
from app.schemas import Order, ReviewRequest, ReviewSummary

router = APIRouter(tags=["Reviews"])


@router.post("/api/orders/{reference}/review", response_model=Order, status_code=status.HTTP_201_CREATED)
def review_order(reference: str, body: ReviewRequest, user: dict = Depends(require_customer)):
    """A customer reviews one of their own orders once it has been served, once."""
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        order = connection.execute("SELECT id, status FROM orders WHERE reference = ? AND user_id = ?",
                                   (reference.upper(), user["id"])).fetchone()
        # Another customer's order looks exactly like one that does not exist.
        if order is None:
            raise HTTPException(404, "Order not found")
        if order["status"] != "served":
            raise HTTPException(409, "You can review an order once it has been served")
        if connection.execute("SELECT 1 FROM reviews WHERE order_id = ?", (order["id"],)).fetchone():
            raise HTTPException(409, "You have already reviewed this order")
        try:
            connection.execute(
                "INSERT INTO reviews (user_id, order_id, rating, comment, created_at) VALUES (?, ?, ?, ?, ?)",
                (user["id"], order["id"], body.rating, body.comment, now_text()))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "You have already reviewed this order")
        return load_orders(connection, "id = ?", (order["id"],))[0]


@router.get("/api/reviews", response_model=ReviewSummary)
def recent_reviews(limit: int = Query(default=6, ge=1, le=20)):
    """Public: average rating and the latest written reviews.

    Only the author's first name is shown, contact details in comments are
    removed, and comments that look like instructions to an AI are not shown.
    """
    with get_connection() as connection:
        stats = connection.execute("SELECT COUNT(*) AS n, AVG(rating) AS average FROM reviews").fetchone()
        rows = connection.execute(
            """SELECT r.rating, r.comment, r.created_at, u.full_name FROM reviews r LEFT JOIN users u ON u.id = r.user_id
               WHERE TRIM(COALESCE(r.comment, '')) != '' ORDER BY r.created_at DESC, r.id DESC LIMIT ?""",
            (limit * 3,)).fetchall()
        names = [row[0] for row in connection.execute("SELECT full_name FROM users")]
    reviews = []
    for row in rows:
        if INJECTION.search(row["comment"]):
            continue
        first_name = (row["full_name"] or "").split(" ")[0] or "Guest"
        reviews.append({"rating": row["rating"], "comment": redact(row["comment"], names), "author": first_name,
                        "created_at": row["created_at"]})
        if len(reviews) == limit:
            break
    return {"average_rating": round(stats["average"], 2) if stats["average"] is not None else None,
            "review_count": stats["n"], "reviews": reviews}
