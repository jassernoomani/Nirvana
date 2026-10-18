import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status  # type: ignore

from app.auth import require_staff
from app.database import get_connection
from app.schemas import MenuItem, MenuItemCreate, MenuItemPatch, MenuPage

router = APIRouter(prefix="/api/menu", tags=["Menu"])
# Reading the menu is public; every change requires a staff session.
STAFF_ONLY = [Depends(require_staff)]


def row_to_menu_item(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["is_available"] = bool(item["is_available"])
    item["is_vegetarian"] = bool(item["is_vegetarian"])
    return item


@router.get("", response_model=list[MenuItem])
def list_menu_items(
    category: str | None = None,
    available: bool | None = None,
    search: str | None = Query(default=None, max_length=100),
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    vegetarian: bool | None = None,
    sort: Literal["name", "price", "category", "id"] = "category",
    direction: Literal["asc", "desc"] = "asc",
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(status_code=422, detail="min_price must not exceed max_price")
    query = "SELECT * FROM menu_items"
    conditions = []
    parameters = []

    if category:
        conditions.append("category = ?")
        parameters.append(category)

    if available is not None:
        conditions.append("is_available = ?")
        parameters.append(int(available))

    if search:
        conditions.append("(instr(lower(name), lower(?)) > 0 OR instr(lower(coalesce(description, '')), lower(?)) > 0)")
        parameters.extend([search, search])
    for value, clause in [(min_price, "price >= ?"), (max_price, "price <= ?"), (vegetarian, "is_vegetarian = ?")]:
        if value is not None:
            conditions.append(clause)
            parameters.append(value)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += f" ORDER BY {sort} {direction}, id ASC LIMIT ? OFFSET ?"
    parameters.extend([limit, offset])

    with get_connection() as connection:
        rows = connection.execute(query, parameters).fetchall()

    return [row_to_menu_item(row) for row in rows]


@router.get("/page", response_model=MenuPage)
def menu_page(page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100)):
    with get_connection() as connection:
        total = connection.execute("SELECT COUNT(*) FROM menu_items").fetchone()[0]
        rows = connection.execute("SELECT * FROM menu_items ORDER BY category, name, id LIMIT ? OFFSET ?", (page_size, (page - 1) * page_size)).fetchall()
    return {"items": [row_to_menu_item(row) for row in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/categories", response_model=list[str])
def list_categories():
    with get_connection() as connection:
        return [row[0] for row in connection.execute("SELECT DISTINCT category FROM menu_items ORDER BY category")]


@router.get("/{item_id}", response_model=MenuItem)
def get_menu_item(item_id: int):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM menu_items WHERE id = ?",
            (item_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Menu item not found")

    return row_to_menu_item(row)


@router.post(
    "",
    response_model=MenuItem,
    status_code=status.HTTP_201_CREATED,
    dependencies=STAFF_ONLY,
)
def create_menu_item(item: MenuItemCreate):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO menu_items (name, description, price, category, is_available, preparation_minutes, is_vegetarian, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.name,
                item.description,
                item.price,
                item.category,
                int(item.is_available),
                item.preparation_minutes,
                int(item.is_vegetarian),
                item.image_url,
            ),
        )
        row = connection.execute(
            "SELECT * FROM menu_items WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()

    return row_to_menu_item(row)


@router.put("/{item_id}", response_model=MenuItem, dependencies=STAFF_ONLY)
def update_menu_item(item_id: int, item: MenuItemCreate):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE menu_items
            SET name = ?, description = ?, price = ?, category = ?, is_available = ?, preparation_minutes = ?, is_vegetarian = ?, image_url = ?
            WHERE id = ?
            """,
            (
                item.name,
                item.description,
                item.price,
                item.category,
                int(item.is_available),
                item.preparation_minutes,
                int(item.is_vegetarian),
                item.image_url,
                item_id,
            ),
        )

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Menu item not found")

        row = connection.execute(
            "SELECT * FROM menu_items WHERE id = ?",
            (item_id,),
        ).fetchone()

    return row_to_menu_item(row)


@router.patch("/{item_id}", response_model=MenuItem, dependencies=STAFF_ONLY)
def patch_menu_item(item_id: int, item: MenuItemPatch):
    changes = item.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Provide at least one field to update")
    with get_connection() as connection:
        if connection.execute("SELECT id FROM menu_items WHERE id = ?", (item_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Menu item not found")
        assignments = ", ".join(f"{field} = ?" for field in changes)
        connection.execute(f"UPDATE menu_items SET {assignments} WHERE id = ?", [*changes.values(), item_id])
        row = connection.execute("SELECT * FROM menu_items WHERE id = ?", (item_id,)).fetchone()
    return row_to_menu_item(row)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=STAFF_ONLY)
def delete_menu_item(item_id: int):
    try:
        with get_connection() as connection:
            cursor = connection.execute(
                "DELETE FROM menu_items WHERE id = ?",
                (item_id,),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="This dish appears in past orders; mark it unavailable instead of deleting it",
        )

    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Menu item not found")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
