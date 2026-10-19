# Restauration frontend

Angular 20 front-end (standalone components, signals, no zone.js) for customers and restaurant staff. All data comes from the FastAPI back-end. Each dish has an AI-generated illustrative food image stored locally under `public/assets/dishes`; these are not photographs of the restaurant's actual dishes.

Start the back-end in a separate terminal, from `backend`:

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Then from `frontend`:

```powershell
npm ci
npm start
```

Development requests to `/api` are proxied to port 8000. For production, configure the web server to forward `/api` to FastAPI and fall back to `index.html` for Angular routes; the development proxy is not part of the production build. `npm run build` produces `dist/restauration/browser`.

## Pages

| Route | Who | What |
|---|---|---|
| `/` | Everyone | Menu with search, filters, dish details with recipe allergens, cart, guest reviews |
| `/login` | Everyone | Sign in and customer sign-up |
| `/recommendations` | Customers | Dietary preferences and dishes picked for the customer |
| `/checkout` | Customers | Review the cart and place an order |
| `/orders`, `/orders/:reference` | Customers | Order history (20 at a time) and order details, with the review form for served orders |
| `/reservations` | Customers | Book a table and manage reservations |
| `/admin` | Staff | Menu studio: create, edit and remove dishes |
| `/admin/kitchen` | Staff | Kitchen board: New, Preparing, Ready |
| `/admin/inventory` | Staff | Ingredient stock, deliveries, adjustments and history |
| `/admin/intelligence` | Staff | Demand forecast, review analysis and the AI prompts |

Route guards only keep navigation tidy; every permission is enforced by the API. The cart is kept in the browser (`localStorage`) so it survives sign-in and reloads; prices shown there are for display only, since the server prices every order.

## Shared building blocks

- `auth.service.ts`: the signed-in user, sign-in, sign-up and `signOut()`.
- `auth.guards.ts`: route guards and the interceptor that sends users back to sign-in when a session expires.
- `customer-nav.ts`, `staff-nav.ts`: the customer header and the staff sidebar links.
- `errors.ts`: `errorMessage()`, the single place that turns a failed API call into a readable message.
- `server-time.ts`: `serverTime()`, which converts the API's local timestamps for `Date` and the date pipe.

## Dish images

The API stores `image_url` as a local `/assets/dishes` path; edits preserve it, and new dishes without an image show a decorative fallback. `dish-image-manifest.json` records the prompts used to generate each image with an AI image generator and the original source files. `prepare_dish_images.py` converted those sources to WebP with Pillow; it needs the original source files, which are only on the machine that generated them. The final WebP files are part of the build and do not depend on any external service.
