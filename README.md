# Nirvana

Desktop restaurant web application built with Angular, FastAPI, and SQLite.

- Customer menu: browse dishes, filter categories, view details, and build a cart.
- Staff dashboard: create and edit dishes, manage availability, and delete dishes.
- Includes 28 sample dishes across 7 categories and 27 locally stored AI-generated dish illustrations.

## Run locally on Windows

Requirements: Python 3.12 and Node.js compatible with Angular 20 (the project was built using Node.js 22).

Backend, in one PowerShell terminal:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Frontend, in a second terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd start
```

- Customer menu: http://localhost:4200
- Staff dashboard: http://localhost:4200/admin
- API documentation: http://localhost:8000/docs

The Angular development server proxies API requests to port 8000. See the backend and frontend READMEs for API and deployment details.

## Validation

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest test_menu -v
```

From frontend, run `npm.cmd run build` for a production build.

The cart is a UI preview: order submission and payment are not implemented. Staff routes and mutation APIs do not yet have authentication. The bundled SQLite database contains sample menu data; backup databases and local environments are excluded from Git.
