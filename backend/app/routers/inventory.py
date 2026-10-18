from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException  # type: ignore

from app.auth import require_staff
from app.database import get_connection
from app.schemas import InventoryItem, StockAdjustment, StockMovement, StockUpdate

# Every inventory route is staff-only.
router = APIRouter(prefix="/api/inventory", tags=["Inventory"], dependencies=[Depends(require_staff)])

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
# Floating-point tolerance for quantities such as 0.25 of a lemon.
EPSILON = 1e-9


def stock_status(quantity: float, minimum: float) -> str:
    if quantity <= EPSILON:
        return "out"
    return "low" if quantity < minimum else "ok"


def tidy(value: float) -> float:
    """Round away float noise (0.1 + 0.2) without hiding real fractions."""
    return round(value, 3)


def load_items(connection, where: str = "1 = 1", parameters: tuple = ()) -> list[dict]:
    rows = connection.execute(
        f"""SELECT i.id, i.name, i.unit, i.stock_quantity, i.reorder_level,
                   (SELECT group_concat(name, '|') FROM (
                        SELECT m.name FROM dish_ingredients di JOIN menu_items m ON m.id = di.menu_item_id
                        WHERE di.ingredient_id = i.id ORDER BY m.name)) AS used_in
            FROM ingredients i WHERE {where} ORDER BY i.name""", parameters).fetchall()
    return [{"id": r["id"], "name": r["name"], "unit": r["unit"], "stock_quantity": tidy(r["stock_quantity"]),
             "reorder_level": tidy(r["reorder_level"]), "status": stock_status(r["stock_quantity"], r["reorder_level"]),
             "used_in": r["used_in"].split("|") if r["used_in"] else []} for r in rows]


def record(connection, ingredient_id: int, change: float, reason: str, note: str | None, staff_id: int | None,
           order_id: int | None = None) -> None:
    after = connection.execute("SELECT stock_quantity FROM ingredients WHERE id = ?", (ingredient_id,)).fetchone()[0]
    connection.execute(
        "INSERT INTO stock_movements (ingredient_id, change, quantity_after, reason, note, staff_id, order_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (ingredient_id, tidy(change), tidy(max(after, 0)), reason, note, staff_id, order_id,
         datetime.now().strftime(TIME_FORMAT)))


def get_item(connection, ingredient_id: int) -> dict:
    items = load_items(connection, "i.id = ?", (ingredient_id,))
    if not items:
        raise HTTPException(404, "Ingredient not found")
    return items[0]


@router.get("", response_model=list[InventoryItem])
def list_inventory():
    with get_connection() as connection:
        return load_items(connection)


@router.post("/{ingredient_id}/adjust", response_model=InventoryItem)
def adjust_stock(ingredient_id: int, body: StockAdjustment, staff: dict = Depends(require_staff)):
    if abs(body.change) <= EPSILON:
        raise HTTPException(422, "Enter a quantity other than zero")
    if body.reason == "delivery" and body.change < 0:
        raise HTTPException(422, "A delivery must add stock. Use a correction or waste to remove stock")
    if body.reason == "waste" and body.change > 0:
        raise HTTPException(422, "Waste removes stock. Use a delivery or correction to add stock")
    note = body.note.strip() if body.note and body.note.strip() else None
    with get_connection() as connection:
        item = get_item(connection, ingredient_id)
        # The condition makes the check and the change one atomic statement, so a
        # concurrent order cannot slip in between and push stock below zero.
        updated = connection.execute(
            "UPDATE ingredients SET stock_quantity = stock_quantity + ? WHERE id = ? AND stock_quantity + ? >= -?",
            (body.change, ingredient_id, body.change, EPSILON)).rowcount
        if not updated:
            current = connection.execute("SELECT stock_quantity FROM ingredients WHERE id = ?", (ingredient_id,)).fetchone()[0]
            raise HTTPException(409, f"Stock cannot go below zero: only {tidy(current):g} {item['unit']} of "
                                     f"{item['name']} in stock")
        # Clamp float noise such as -1e-12 to exactly zero.
        connection.execute("UPDATE ingredients SET stock_quantity = 0 WHERE id = ? AND stock_quantity < 0", (ingredient_id,))
        record(connection, ingredient_id, body.change, body.reason, note, staff["id"])
        return get_item(connection, ingredient_id)


@router.put("/{ingredient_id}", response_model=InventoryItem)
def update_stock(ingredient_id: int, body: StockUpdate, staff: dict = Depends(require_staff)):
    if body.stock_quantity is None and body.reorder_level is None:
        raise HTTPException(422, "Provide a stock quantity or a minimum level to update")
    note = body.note.strip() if body.note and body.note.strip() else None
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        before = get_item(connection, ingredient_id)
        if body.reorder_level is not None:
            connection.execute("UPDATE ingredients SET reorder_level = ? WHERE id = ?", (body.reorder_level, ingredient_id))
        if body.stock_quantity is not None:
            change = body.stock_quantity - before["stock_quantity"]
            connection.execute("UPDATE ingredients SET stock_quantity = ? WHERE id = ?", (body.stock_quantity, ingredient_id))
            if abs(change) > EPSILON:
                record(connection, ingredient_id, change, "count", note, staff["id"])
        return get_item(connection, ingredient_id)


@router.get("/{ingredient_id}/movements", response_model=list[StockMovement])
def stock_history(ingredient_id: int):
    with get_connection() as connection:
        get_item(connection, ingredient_id)
        return [dict(row) for row in connection.execute(
            """SELECT s.id, s.change, s.quantity_after, s.reason, s.note, u.full_name AS staff_name,
                      o.reference AS order_reference, s.created_at
               FROM stock_movements s LEFT JOIN users u ON u.id = s.staff_id LEFT JOIN orders o ON o.id = s.order_id
               WHERE s.ingredient_id = ? ORDER BY s.created_at DESC, s.id DESC LIMIT 50""", (ingredient_id,))]
