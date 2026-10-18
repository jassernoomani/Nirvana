# Restaurant API

Run from this directory using the project's Python environment:

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Interactive API documentation: http://localhost:8000/docs

Menu routes:

- `GET /api/menu`: returns a list. Supports `category`, `available`, `search`, `min_price`, `max_price`, `vegetarian`, `sort` (name, price, category, id), `direction` (asc, desc), `limit` (1–100, default 100), and `offset`.
- `GET /api/menu/page?page=1&page_size=20`: returns items, total, page, and page_size for the complete menu.
- `GET /api/menu/categories`: lists current categories.
- `POST /api/menu`: creates a dish.
- `GET /api/menu/{id}`: gets a dish.
- `PUT /api/menu/{id}`: replaces a dish.
- `PATCH /api/menu/{id}`: updates only supplied fields; description can be cleared with null.
- `DELETE /api/menu/{id}`: deletes a dish.

Each dish includes name, description, price, category, availability, preparation_minutes (1–240, default 15), and is_vegetarian (default false). Currency is not yet configured. Existing dishes receive these defaults on startup; all original rows are preserved. Existing duplicate dishes are retained.

Startup performs an additive, repeatable SQLite migration. The list route now returns at most 100 dishes by default; clients with larger menus must use offset or the page endpoint.

For tests, install requirements-dev.txt in your environment and run:

```powershell
.venv/Scripts/python.exe -m unittest test_menu -v
```

Tests use temporary databases. This API currently has no authentication; administrative routes require access control before public deployment.
