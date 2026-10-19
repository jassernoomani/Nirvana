# Nirvana: no-show prediction

A fourth intelligence module, added next to the three described in [AI_MODULES.md](AI_MODULES.md). It estimates the probability that each upcoming reservation will not turn up, suggests a careful amount of overbooking per service and targets automatic reminders at the bookings that need one. It uses scikit-learn only: no language model, no cloud call, nothing sent outside the machine.

Existing features, endpoints, tables and tests are untouched. The module is additive: one new table (`reservation_reminders`), new files, and one-line registrations (router in `backend/app/main.py`, route in `frontend/src/main.ts`, link in `frontend/src/app/staff-nav.ts`).

## Where to use it

| What | Where | Access |
|---|---|---|
| Page | `/admin/noshow` ("No-shows" in the staff sidebar) | Staff |
| API | `/api/ai/noshow/...` (table below) | Staff |
| Automatic cycle | `backend/run_noshow_reminders.py` | Scheduler (cron / Task Scheduler) |

## The classifier

- Target: a past reservation is a no-show (`no_show`) or honoured (`completed`, `seated`). Cancelled and still-open reservations are not used as targets: a cancellation frees the table, which is a different outcome.
- Features: hour and weekday (cyclic), dinner vs lunch, weekend, party size and large party (6+), how many days ahead the booking was made, phone number given, notes given, and the customer's history: number of past visits, smoothed past no-show rate, smoothed past cancellation rate, first-time guest.
- History is computed strictly from reservations that took place **before** the one scored, so training never sees the future. The customer's rate is pulled towards the restaurant's rate with four pseudo-observations, so one miss does not brand a new customer.
- Model: standardisation + `LogisticRegression` (C = 0.3, seed 42). Probabilities are not rebalanced, so they stay interpretable as chances.
- Validation: chronological. The latest quarter of resolved reservations is held out; the model is trained on the earlier ones. Reported: Brier score of the model and of a flat base-rate baseline, AUC, and the observed no-show rate in the riskiest quarter of the holdout against the rest.
- Honest selection: if the model does not beat the flat rate on the holdout, the flat rate is used for everyone, every reservation is labelled "Average" and no reminder is planned. The page says so.
- Minimum data: 80 completed or missed reservations including 8 no-shows, otherwise the API answers 422 with the reason.
- Explanations: for each reservation the three factors that move its score most are listed as plain facts ("Party of 8", "12 no-shows in 21 past visits") with the direction of their effect.

## Overbooking advice

For each service (lunch before 16:00, dinner after) of each day, the exact distribution of the number of no-shows is computed from the individual probabilities (Poisson-binomial, parties assumed independent). The suggestion is the largest number `k` of extra bookings such that the chance of fewer than `k` no-shows stays at or under the tolerance (default 10%), never above `NOSHOW_OVERBOOK_MAX` (default 2) nor above the expected number of no-shows. Small services therefore usually get no suggestion.

This is advice for staff. Online booking in `routers/reservations.py` is unchanged and still refuses to double-book a table.

## Targeted reminders

- Who: reservations at medium risk (default from 15%) or high risk (default from 30%). With the flat-rate fallback, nobody.
- When: 24 hours before, or immediately when the booking is sooner; high risk gets a second one 3 hours before, if at least 6 hours separate the two. Nothing is planned later than one hour before the booking.
- What: a fixed template that asks the guest to cancel from the Reservations page if plans changed. It never mentions the prediction.
- Channel: SMS when the reservation has a phone number, otherwise e-mail.
- Safety: one reminder per reservation and kind (re-running creates no duplicates). At dispatch time a reminder is skipped if the reservation is no longer `booked` or starts within 30 minutes. A delivery error keeps the reminder pending for the next run.
- Delivery: the project has no SMS or e-mail provider, so dispatched reminders are appended to `backend/app/noshow_outbox.jsonl` (one JSON object per line: channel, recipient, message). A messaging service can consume that file, or `write_outbox` in `app/ai/noshow.py` can be replaced by a real sender. Reminders are marked "dispatched" when handed to the outbox, which is not proof of delivery.

Run the whole cycle automatically every 30 minutes, from `backend`:

```powershell
# Windows Task Scheduler action
.\.venv\Scripts\python.exe run_noshow_reminders.py
```

```cron
*/30 * * * * cd /path/to/backend && .venv/bin/python run_noshow_reminders.py
```

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/ai/noshow/overview?days=7` | Metrics, risk per reservation, advice per service, reminder plan. `days` from 1 to 14 |
| POST | `/api/ai/noshow/reminders/schedule?days=7` | Stores the plan. Idempotent |
| POST | `/api/ai/noshow/reminders/dispatch` | Hands due reminders to the outbox |
| GET | `/api/ai/noshow/reminders?limit=50` | Stored reminders, newest first |

All four require a staff session. The report contains guest names but no phone number or e-mail address; contact details are only written to the outbox.

## Configuration

Optional environment variables (see `backend/.env.example`): `NOSHOW_MEDIUM_RISK`, `NOSHOW_HIGH_RISK`, `NOSHOW_OVERBOOK_TOLERANCE`, `NOSHOW_OVERBOOK_MAX`, `NOSHOW_RESTAURANT_NAME`, `NOSHOW_OUTBOX_PATH`. Restart the backend after changing them.

## Demo data

`seed_data.py` draws every past outcome at random (about 7% no-shows whatever the booking), so there is nothing to learn: on a freshly seeded database the page correctly falls back to the base rate. To see the module work, add reservations whose no-shows have causes (large parties, weekend dinners, same-day bookings, no phone, a few habitual no-show customers):

```powershell
.\.venv\Scripts\python.exe seed_noshow_demo.py            # add
.\.venv\Scripts\python.exe seed_noshow_demo.py --remove   # remove again
```

The rows it adds have no table assigned, so they never block a table in the booking engine. The effect it demonstrates is built into this synthetic data; it is not evidence about real guests. On real data, expect weaker signals and check the holdout figures before trusting the targeting.

## Limits

- Probabilities are estimates from past reservations, not certainties, and they drift when habits change: retraining happens at every request, on the data available then.
- Parties are treated as independent, which understates the risk for groups that cancel together.
- Reservations made before the `contact_phone` column existed have no phone; the model sees that as "no phone".
- Customers are identified by account. A guest with several accounts has several histories.

## Verification

```powershell
# From backend:
.\.venv\Scripts\python.exe -m unittest test_noshow -v
.\.venv\Scripts\python.exe -m unittest discover -p "test_*.py" -v
# From frontend:
npm.cmd run build
```

`test_noshow.py` covers access control, absence of look-ahead in the history features, the overbooking arithmetic, the honest fallback, idempotent scheduling, skipped and failed dispatches, and the guarantee that no reservation is modified.
