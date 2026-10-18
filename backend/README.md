# Restaurant API

Run from this directory using the project's Python environment:

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Create the demo database first (deletes and rebuilds `app/restaurant.db`):

```powershell
.venv/Scripts/python.exe seed_data.py --reset
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

Startup performs an additive, repeatable SQLite migration that also creates the tables below.

## Data model

| Table | Purpose |
|---|---|
| `menu_items` | Dishes (existing) |
| `ingredients` | Stock quantity and reorder level per ingredient, in g, ml or pieces |
| `dish_ingredients` | Recipe: quantity of each ingredient per portion |
| `allergens`, `ingredient_allergens` | Allergens per ingredient; a dish's allergens come from its recipe |
| `users` | Customers and staff, with PBKDF2 password hashes and a vegetarian flag |
| `user_allergies`, `user_favorite_categories` | Customer dietary profile used by recommendations |
| `orders`, `order_items` | Orders with status (pending, preparing, ready, served, cancelled) and the price paid per item |
| `reviews` | Rating (1–5) and comment, optionally linked to an order |
| `restaurant_tables`, `reservations` | Tables with seat counts and bookings |

Foreign keys are enforced. A dish that appears in past orders cannot be deleted (409); mark it unavailable instead.

`seed_data.py` fills these tables with reproducible demo data: 120 customers, about 90 days of orders with lunch and dinner peaks and busier weekends, reviews whose complaints follow patterns (slow service rising on recent Friday and Saturday dinners, cold hot dishes), some ingredients below their reorder level, a few live kitchen orders and upcoming reservations. Three reviews are edge cases for the review analysis module: one containing contact details, one containing a prompt-injection attempt and one in French.

The list route now returns at most 100 dishes by default; clients with larger menus must use offset or the page endpoint.

For tests, install requirements-dev.txt in your environment and run:

```powershell
.venv/Scripts/python.exe -m unittest test_menu test_data_model -v
```

Tests use temporary databases. This API currently has no authentication; administrative routes require access control before public deployment.
