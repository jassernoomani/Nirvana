# Nirvana

Desktop restaurant web application built with Angular, FastAPI, and SQLite.

Local intelligence modules are now available: customer recommendations at `/recommendations`, and staff demand forecasting / review analysis at `/admin/intelligence`. See [AI_MODULES.md](AI_MODULES.md) for setup and methodology, and [AI_PROMPTS.md](AI_PROMPTS.md) for the exact local-model prompts. Configured local model: `qwen2.5:3b` through Ollama; forecasting uses scikit-learn.

- Customer menu: browse dishes, filter categories, view details, and build a cart.
- Checkout: customers confirm their cart to place an order, then see the confirmation and their order history.
- Reviews: customers rate and comment on their served orders; the menu page shows recent guest reviews.
- Reservations: customers book a table for a date, time and party size, see their reservations and cancel upcoming ones.
- Staff dashboard: create and edit dishes, manage availability, and delete dishes.
- Kitchen dashboard (staff): open orders in New, Preparing and Ready columns, advanced with one click.
- Inventory (staff): ingredient stock with low-stock warnings, deliveries, adjustments, stock counts and a history of every change.
- Accounts: sign-up for customers, sign-in and sign-out, with customer and staff roles enforced by the API.
- Includes 27 sample dishes across 7 categories, each with a local illustration, a recipe and allergens.
- A seed script generates 90 days of demo data: customers, orders, reviews, reservations and ingredient stock.

## Run locally on Windows

Requirements: Python 3.12 and Node.js compatible with Angular 20 (the project was built using Node.js 22).

Backend, in one PowerShell terminal:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe seed_data.py --reset
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Frontend, in a second terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd start
```

- Customer menu: http://localhost:4200
- Sign in or create an account: http://localhost:4200/login
- Staff dashboard (staff accounts only): http://localhost:4200/admin
- Kitchen dashboard (staff accounts only): http://localhost:4200/admin/kitchen
- Inventory (staff accounts only): http://localhost:4200/admin/inventory
- API documentation: http://localhost:8000/docs

`seed_data.py --reset` deletes and rebuilds `backend/app/restaurant.db`. The database is not tracked by Git, so run it after cloning, and again before a demo so the live orders and upcoming reservations are current.

## Demo accounts

All seeded accounts use the password `nirvana-demo`.

| Email | Role | Notes |
|---|---|---|
| `manager@nirvana.test` | staff | Restaurant manager |
| `kitchen@nirvana.test` | staff | Kitchen team |
| `demo@nirvana.test` | customer | Allergic to shellfish and molluscs; prefers pasta and desserts; has an order history |

To create your own local account (the password is asked for at the prompt, never stored in code), from `backend`:

```powershell
.\.venv\Scripts\python.exe create_user.py --email you@example.com --name "Your Name" --role staff
```

Public sign-up always creates customer accounts; staff accounts can only be created with this command or by the seed script.

The Angular development server proxies API requests to port 8000. See the backend and frontend READMEs for API and deployment details.

## Validation

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -p "test_*.py" -v
```

To measure coverage, run `.\.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing` from `backend`. [AI_TESTING_AND_REVIEW.md](AI_TESTING_AND_REVIEW.md) describes the AI-assisted security and code review: findings, fixes and coverage before and after.

From frontend, run `npm.cmd run build` for a production build.

Online payment is not implemented: orders are placed without payment. The SQLite database is generated locally by the seed script; it and local environments are excluded from Git.
