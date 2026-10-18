# Restauration frontend

Angular customer menu and staff management dashboard. Menu records come from the database. Each current dish has an AI-generated illustrative food image stored locally under public/assets/dishes; these are not photographs of the restaurant's actual dishes.

Start the backend in a separate terminal, from `backend`:

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Then from `frontend`:

```powershell
npm install
npm start
```

Open http://localhost:4200 for the customer menu and http://localhost:4200/admin for the staff dashboard. These routes are not access controlled yet. Development requests to `/api` are proxied to port 8000. For production, configure your web server to forward `/api` to FastAPI and fall back to index.html for Angular routes; the development proxy is not included in the production build.

`npm run build` produces `dist/restauration/browser`.

Features: menu search, category/availability/vegetarian/price filters, sorting, pagination, creation, editing, availability updates, confirmed deletion, and API error feedback. Cards display stored prices without assuming a currency. Summary counts explicitly refer to the current page. Existing vegetarian flags are defaults and should be verified by the team.

Customer features: live menu browsing, dish details, category/search/vegetarian filters, sorting, pagination, and a visit-only cart with quantities (up to 99 per dish) and subtotal. Unavailable dishes cannot be added. Refreshing the page clears the cart. No order submission, payment, taxes, fees, or checkout backend exists yet; the cart explicitly states that no order has been placed. Customer pages do not expose administrative actions. The full menu is fetched through the paginated endpoint so dishes beyond the API's 100-row limit remain accessible.

Images appear in customer cards, details, cart thumbnails, and admin cards. The API stores image_url as a local /assets/dishes path; edits preserve it. New dishes without an assigned image retain the decorative fallback. The two duplicate Margherita records share an image. dish-image-manifest.json records the prompts and generated source files (built-in image generation); prepare_dish_images.py optimizes these sources with Pillow. Final WebP files are included in production builds and do not depend on external image services. backend/assign_dish_images.py assigns the current set after taking a SQLite backup.
