import math
import secrets
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status  # type: ignore

from app.auth import current_user, require_customer
from app.database import get_connection
from app.schemas import CheckoutRequest, Order

router = APIRouter(prefix="/api/orders", tags=["Orders"])

# No 0/O or 1/I, so references are easy to read out loud.
REFERENCE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
MAX_PER_DISH = 99


def make_reference(choice=secrets.choice) -> str:
    return "NV-" + "".join(choice(REFERENCE_ALPHABET) for _ in range(8))


def load_orders(connection: sqlite3.Connection, where: str, parameters: tuple, limit: int = 1) -> list[dict]:
    orders = [dict(row) for row in connection.execute(
        f"SELECT id, reference, status, total, created_at FROM orders WHERE {where} "
        "ORDER BY created_at DESC, id DESC LIMIT ?", (*parameters, limit))]
    if not orders:
        return []
    by_id = {order["id"]: {**order, "items": []} for order in orders}
    marks = ", ".join("?" * len(by_id))
    for row in connection.execute(
            f"""SELECT oi.order_id, oi.menu_item_id, m.name, oi.quantity, oi.unit_price
                FROM order_items oi JOIN menu_items m ON m.id = oi.menu_item_id
                WHERE oi.order_id IN ({marks}) ORDER BY m.name""", tuple(by_id)):
        by_id[row["order_id"]]["items"].append({
            "menu_item_id": row["menu_item_id"], "name": row["name"], "quantity": row["quantity"],
            "unit_price": row["unit_price"], "line_total": round(row["unit_price"] * row["quantity"], 2)})
    return list(by_id.values())


@router.post("", response_model=Order, status_code=status.HTTP_201_CREATED)
def place_order(body: CheckoutRequest, response: Response, user: dict = Depends(require_customer)):
    if not body.items:
        raise HTTPException(status_code=422, detail="Your cart is empty")
    quantities = Counter()
    for line in body.items:
        quantities[line.menu_item_id] += line.quantity
    if any(quantity > MAX_PER_DISH for quantity in quantities.values()):
        raise HTTPException(status_code=422, detail=f"You can order at most {MAX_PER_DISH} of each dish")
    marks = ", ".join("?" * len(quantities))

    with get_connection() as connection:
        # Take the write lock before reading, so concurrent checkouts cannot both
        # pass the stock check, and a resubmitted checkout sees the first one.
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute("SELECT id FROM orders WHERE user_id = ? AND idempotency_key = ?",
                                      (user["id"], body.idempotency_key)).fetchone()
        if existing:
            response.status_code = status.HTTP_200_OK
            return load_orders(connection, "id = ?", (existing["id"],))[0]

        dishes = {row["id"]: row for row in connection.execute(
            f"SELECT id, name, price, is_available FROM menu_items WHERE id IN ({marks})", tuple(quantities))}
        missing = sorted(set(quantities) - set(dishes))
        if missing:
            raise HTTPException(status_code=422, detail=f"These dishes are not on the menu: {', '.join(map(str, missing))}. "
                                                         "Please refresh the menu and update your cart")
        unavailable = [dishes[d]["name"] for d in quantities if not dishes[d]["is_available"]]
        if unavailable:
            raise HTTPException(status_code=409, detail=f"No longer available: {', '.join(unavailable)}. "
                                                         "Please remove them from your cart")

        # Stock is tracked per ingredient: total what the whole order needs.
        recipes = defaultdict(list)
        stock, required = {}, Counter()
        for row in connection.execute(
                f"""SELECT di.menu_item_id, di.ingredient_id, di.quantity, i.stock_quantity
                    FROM dish_ingredients di JOIN ingredients i ON i.id = di.ingredient_id
                    WHERE di.menu_item_id IN ({marks})""", tuple(quantities)):
            recipes[row["menu_item_id"]].append((row["ingredient_id"], row["quantity"]))
            stock[row["ingredient_id"]] = row["stock_quantity"]
            required[row["ingredient_id"]] += row["quantity"] * quantities[row["menu_item_id"]]
        short = {ingredient for ingredient, amount in required.items() if amount > stock[ingredient] + 1e-9}
        if short:
            problems = []
            for dish_id in quantities:
                if any(ingredient in short for ingredient, _ in recipes[dish_id]):
                    left = min(math.floor(stock[i] / portion + 1e-9) for i, portion in recipes[dish_id])
                    problems.append(f"{dishes[dish_id]['name']} (we can prepare {left} more)" if left else
                                    f"{dishes[dish_id]['name']} (sold out for now)")
            raise HTTPException(status_code=409, detail=f"Not enough ingredients for: {', '.join(problems)}. "
                                                         "Please reduce the quantity or choose another dish")

        # Prices come from the database, never from the client, and are copied
        # into each order item so later menu price changes do not alter the order.
        total = round(sum(dishes[d]["price"] * q for d, q in quantities.items()), 2)
        reference = make_reference()
        while connection.execute("SELECT 1 FROM orders WHERE reference = ?", (reference,)).fetchone():
            reference = make_reference()
        order_id = connection.execute(
            "INSERT INTO orders (user_id, status, total, created_at, reference, idempotency_key) "
            "VALUES (?, 'pending', ?, ?, ?, ?)",
            (user["id"], total, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), reference, body.idempotency_key)).lastrowid
        connection.executemany("INSERT INTO order_items (order_id, menu_item_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                               [(order_id, d, q, dishes[d]["price"]) for d, q in quantities.items()])
        for ingredient, amount in required.items():
            updated = connection.execute(
                "UPDATE ingredients SET stock_quantity = stock_quantity - ? WHERE id = ? AND stock_quantity >= ? - 1e-9",
                (amount, ingredient, amount)).rowcount
            if not updated:  # Rolls back the whole order.
                raise HTTPException(status_code=409, detail="Stock changed while placing your order. Please try again")
        return load_orders(connection, "id = ?", (order_id,))[0]


@router.get("", response_model=list[Order])
def my_orders(user: dict = Depends(require_customer)):
    with get_connection() as connection:
        return load_orders(connection, "user_id = ?", (user["id"],), limit=50)


@router.get("/{reference}", response_model=Order)
def get_order(reference: str, user: dict = Depends(current_user)):
    # Customers only see their own orders; another customer's order looks like it does not exist.
    where, parameters = ("reference = ?", (reference.upper(),)) if user["role"] == "staff" else \
        ("reference = ? AND user_id = ?", (reference.upper(), user["id"]))
    with get_connection() as connection:
        orders = load_orders(connection, where, parameters)
    if not orders:
        raise HTTPException(status_code=404, detail="Order not found")
    return orders[0]
