from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException  # type: ignore

from app.auth import require_staff
from app.database import get_connection
from app.schemas import KitchenOrder, StatusChange

# Every kitchen route is staff-only.
router = APIRouter(prefix="/api/kitchen", tags=["Kitchen"], dependencies=[Depends(require_staff)])

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
# The kitchen workflow. "pending" is shown as New; serving an order removes it from the board.
NEXT_STATUS = {"pending": "preparing", "preparing": "ready", "ready": "served"}
ACTIVE = ("pending", "preparing", "ready")
# Items are listed in the order a kitchen sends them out, not alphabetically.
COURSE_ORDER = """CASE m.category WHEN 'Starters' THEN 1 WHEN 'Salads' THEN 2 WHEN 'Pizza' THEN 3 WHEN 'Pasta' THEN 4
    WHEN 'Mains' THEN 5 WHEN 'Desserts' THEN 6 WHEN 'Drinks' THEN 7 ELSE 8 END"""


def load(connection, where: str, parameters: tuple) -> list[dict]:
    rows = connection.execute(
        f"""SELECT o.id, o.reference, o.status, o.created_at, u.full_name AS customer_name,
                   COALESCE((SELECT MAX(changed_at) FROM order_status_history h WHERE h.order_id = o.id), o.created_at) AS status_since
            FROM orders o LEFT JOIN users u ON u.id = o.user_id
            WHERE {where} ORDER BY o.created_at, o.id""", parameters).fetchall()
    orders = {row["id"]: {**dict(row), "items": [], "item_count": 0, "longest_preparation_minutes": 0} for row in rows}
    if orders:
        marks = ", ".join("?" * len(orders))
        for item in connection.execute(
                f"""SELECT oi.order_id, oi.menu_item_id, m.name, oi.quantity, oi.unit_price, m.preparation_minutes
                    FROM order_items oi JOIN menu_items m ON m.id = oi.menu_item_id
                    WHERE oi.order_id IN ({marks}) ORDER BY {COURSE_ORDER}, m.name""", tuple(orders)):
            order = orders[item["order_id"]]
            order["items"].append({"menu_item_id": item["menu_item_id"], "name": item["name"], "quantity": item["quantity"],
                                   "unit_price": item["unit_price"], "line_total": round(item["unit_price"] * item["quantity"], 2)})
            order["item_count"] += item["quantity"]
            order["longest_preparation_minutes"] = max(order["longest_preparation_minutes"], item["preparation_minutes"])
    return list(orders.values())


@router.get("/orders", response_model=list[KitchenOrder])
def kitchen_orders():
    """Open orders, oldest first, so the kitchen works through them in arrival order."""
    with get_connection() as connection:
        return load(connection, f"o.status IN {ACTIVE}", ())


@router.post("/orders/{order_id}/status", response_model=KitchenOrder)
def change_status(order_id: int, body: StatusChange, staff: dict = Depends(require_staff)):
    if NEXT_STATUS.get(body.from_status) != body.to_status:
        raise HTTPException(422, f"An order cannot go from {body.from_status} to {body.to_status}")
    now = datetime.now().strftime(TIME_FORMAT)
    with get_connection() as connection:
        # Conditional on the status the screen showed: if two screens act on the
        # same order, only the first change applies.
        updated = connection.execute(
            "UPDATE orders SET status = ?, completed_at = CASE WHEN ? = 'served' THEN ? ELSE completed_at END "
            "WHERE id = ? AND status = ?",
            (body.to_status, body.to_status, now, order_id, body.from_status)).rowcount
        if not updated:
            row = connection.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
            if row is None:
                raise HTTPException(404, "Order not found")
            raise HTTPException(409, f"This order is already {row['status']}. The board has been refreshed")
        connection.execute(
            "INSERT INTO order_status_history (order_id, from_status, to_status, staff_id, changed_at) VALUES (?, ?, ?, ?, ?)",
            (order_id, body.from_status, body.to_status, staff["id"], now))
        return load(connection, "o.id = ?", (order_id,))[0]
