"""No-show prediction for table reservations, overbooking advice and targeted reminders.

A logistic-regression classifier (scikit-learn, no LLM) estimates, for every upcoming
confirmed reservation, the probability that the party will not turn up. Inputs are the
day and hour of the booking, the party size, how far ahead it was made, whether a phone
number and notes were given, and the customer's own history (earlier no-shows and
cancellations). History features only use reservations that took place *before* the one
being scored, so training never sees the future.

The model is validated on the most recent quarter of resolved reservations (chronological
holdout) and compared with a constant base-rate baseline; when the baseline is at least as
good, the report says so and uses the base rate instead of pretending to see a signal.

On top of the probabilities the module offers two decision aids, both advisory:

* Overbooking: for each service (lunch / dinner of a day) the exact distribution of the
  number of no-shows is computed and a small number of extra bookings is suggested only
  while the chance of ending up with more guests than tables stays under a tolerance.
* Targeted reminders: only reservations at medium or high risk receive a reminder, planned
  24 hours ahead (plus a same-day one for high risk). Messages are fixed templates.

Nothing here changes the booking engine, the reservation status or any table assignment.
"""
import json
import math
import os
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import HTTPException

from app.database import get_connection

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _number(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.getenv(name, default))
    except ValueError:
        return default
    return value if low <= value <= high else default


# Tunable without touching the code, like the booking rules in routers/reservations.py.
MEDIUM_RISK = _number("NOSHOW_MEDIUM_RISK", 0.15, 0.01, 0.95)
HIGH_RISK = max(_number("NOSHOW_HIGH_RISK", 0.30, 0.02, 0.99), MEDIUM_RISK)
OVERBOOK_TOLERANCE = _number("NOSHOW_OVERBOOK_TOLERANCE", 0.10, 0.01, 0.50)
OVERBOOK_MAX = int(_number("NOSHOW_OVERBOOK_MAX", 2, 0, 10))
RESTAURANT_NAME = os.getenv("NOSHOW_RESTAURANT_NAME", "Nirvana")
OUTBOX_PATH = Path(os.getenv("NOSHOW_OUTBOX_PATH") or Path(__file__).resolve().parent.parent / "noshow_outbox.jsonl")

MIN_RESOLVED = 80          # completed or missed reservations needed to train
MIN_NO_SHOWS = 8
HOLDOUT_SHARE = 0.25
HISTORY_DAYS = 365
SMOOTHING = 4              # pseudo-observations pulling a customer's rate towards the restaurant's rate
LUNCH_END_HOUR = 16
LARGE_PARTY = 6
MIN_REMINDER_LEAD = timedelta(minutes=60)   # a reminder later than this before the booking is useless
DISPATCH_CUTOFF = timedelta(minutes=30)

SHOWED = ("completed", "seated")
RESOLVED = SHOWED + ("no_show",)

FEATURES = ["hour_sin", "hour_cos", "dinner", "weekday_sin", "weekday_cos", "weekend", "party_size", "large_party",
            "lead_days", "has_phone", "has_notes", "history_log", "history_no_show_rate", "history_cancel_rate",
            "new_customer"]
# Features are summed into groups so an explanation reads "Party of 8", not "party_size".
GROUPS = {"time": ["hour_sin", "hour_cos", "dinner"], "weekday": ["weekday_sin", "weekday_cos", "weekend"],
          "party": ["party_size", "large_party"], "lead": ["lead_days"], "phone": ["has_phone"],
          "notes": ["has_notes"], "history": ["history_log", "history_no_show_rate", "new_customer"],
          "cancels": ["history_cancel_rate"]}

REMINDER_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS reservation_reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reservation_id INTEGER NOT NULL REFERENCES reservations(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK (kind IN ('day_before', 'same_day')),
        channel TEXT NOT NULL CHECK (channel IN ('sms', 'email')),
        scheduled_for TEXT NOT NULL,
        message TEXT NOT NULL,
        risk REAL NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'dispatched', 'skipped')),
        detail TEXT,
        created_at TEXT NOT NULL,
        dispatched_at TEXT,
        UNIQUE (reservation_id, kind)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_reminders_due ON reservation_reminders(status, scheduled_for)",
]


def now() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


def ensure_schema(connection) -> None:
    """Additive and idempotent: the only table this module owns."""
    for statement in REMINDER_SCHEMA:
        connection.execute(statement)


# --------------------------------------------------------------------------- data

def load_rows(connection, current: datetime) -> list[dict]:
    """Reservations of the last year, oldest first, each with the customer's history *before* it."""
    since = (current - timedelta(days=HISTORY_DAYS)).strftime(TIME_FORMAT)
    raw = connection.execute(
        """SELECT r.id, r.user_id, r.party_size, r.reserved_for, r.status, r.created_at, r.contact_phone, r.notes,
                  u.full_name, u.email, t.label AS table_label
           FROM reservations r JOIN users u ON u.id = r.user_id
           LEFT JOIN restaurant_tables t ON t.id = r.table_id
           WHERE r.reserved_for >= ? ORDER BY r.reserved_for, r.id""", (since,)).fetchall()
    state: dict[int, list[int]] = {}   # user -> [resolved, no_shows, all_past, cancelled]
    rows = []
    for record in raw:
        row = dict(record)
        row["when"] = datetime.fromisoformat(row["reserved_for"])
        try:
            row["made"] = datetime.fromisoformat(row["created_at"])
        except (TypeError, ValueError):
            row["made"] = row["when"]
        history = state.setdefault(row["user_id"], [0, 0, 0, 0])
        row["history"] = tuple(history)
        # Only reservations whose time has passed teach us anything about the customer.
        if row["when"] < current:
            if row["status"] in SHOWED:
                history[0] += 1; history[2] += 1
            elif row["status"] == "no_show":
                history[0] += 1; history[1] += 1; history[2] += 1
            elif row["status"] == "cancelled":
                history[2] += 1; history[3] += 1
        rows.append(row)
    return rows


def vector(row: dict, prior_no_show: float, prior_cancel: float) -> list[float]:
    when, made = row["when"], row["made"]
    hour = when.hour + when.minute / 60
    resolved, no_shows, past, cancelled = row["history"]
    lead = max(0.0, min(60.0, (when - made).total_seconds() / 86400))
    return [math.sin(2 * math.pi * hour / 24), math.cos(2 * math.pi * hour / 24), int(when.hour >= LUNCH_END_HOUR),
            math.sin(2 * math.pi * when.weekday() / 7), math.cos(2 * math.pi * when.weekday() / 7),
            int(when.weekday() >= 5), row["party_size"], int(row["party_size"] >= LARGE_PARTY), math.log1p(lead),
            int(bool(row["contact_phone"])), int(bool((row["notes"] or "").strip())), math.log1p(resolved),
            (no_shows + prior_no_show * SMOOTHING) / (resolved + SMOOTHING),
            (cancelled + prior_cancel * SMOOTHING) / (past + SMOOTHING), int(resolved == 0)]


def priors(rows: list[dict]) -> tuple[float, float]:
    """Restaurant-wide no-show and cancellation rates, from the given (past) rows only."""
    resolved = [r for r in rows if r["status"] in RESOLVED]
    cancelled = sum(1 for r in rows if r["status"] == "cancelled")
    prior_no_show = sum(r["status"] == "no_show" for r in resolved) / max(1, len(resolved))
    prior_cancel = cancelled / max(1, len(resolved) + cancelled)
    return prior_no_show, prior_cancel


def make_model():
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except ImportError as exc:
        raise HTTPException(503, "Install the backend requirements to enable scikit-learn no-show prediction.") from exc
    return Pipeline([("scaler", StandardScaler()), ("clf", LogisticRegression(C=0.3, max_iter=2000, random_state=42))])


def brier(probabilities, outcomes) -> float:
    return sum((p - y) ** 2 for p, y in zip(probabilities, outcomes)) / len(outcomes)


# --------------------------------------------------------------------------- training

def train(rows: list[dict], current: datetime) -> dict:
    """Validate on the latest quarter, pick the better of model and baseline, then refit on everything."""
    past = [r for r in rows if r["when"] < current]
    labelled = [r for r in past if r["status"] in RESOLVED]
    no_shows = sum(r["status"] == "no_show" for r in labelled)
    if len(labelled) < MIN_RESOLVED or no_shows < MIN_NO_SHOWS or no_shows == len(labelled):
        raise HTTPException(422, f"At least {MIN_RESOLVED} completed or missed reservations, including "
                                 f"{MIN_NO_SHOWS} no-shows, are required to train the no-show model.")
    split = int(len(labelled) * (1 - HOLDOUT_SHARE))
    train_rows, test_rows = labelled[:split], labelled[split:]
    if len({r["status"] == "no_show" for r in train_rows}) < 2:
        raise HTTPException(422, "The older reservations contain no no-show yet, so the model cannot be validated.")
    cut = train_rows[-1]["when"]
    prior_ns, prior_c = priors([r for r in past if r["when"] <= cut])
    y_train = [int(r["status"] == "no_show") for r in train_rows]
    y_test = [int(r["status"] == "no_show") for r in test_rows]

    candidate = make_model()
    candidate.fit([vector(r, prior_ns, prior_c) for r in train_rows], y_train)
    scores = [float(p) for p in candidate.predict_proba([vector(r, prior_ns, prior_c) for r in test_rows])[:, 1]]
    model_brier = brier(scores, y_test)
    baseline_brier = brier([prior_ns] * len(y_test), y_test)
    auc = None
    if len(set(y_test)) == 2:
        from sklearn.metrics import roc_auc_score
        auc = float(roc_auc_score(y_test, scores))
    top_rate = rest_rate = None
    top_n = math.ceil(len(scores) / 4)
    if len(scores) >= 8:
        ranked = sorted(range(len(scores)), key=lambda i: -scores[i])
        top, rest = ranked[:top_n], ranked[top_n:]
        top_rate = sum(y_test[i] for i in top) / len(top)
        rest_rate = sum(y_test[i] for i in rest) / len(rest)
    selected = "LogisticRegression" if model_brier < baseline_brier else "base-rate-baseline"

    # Final model: all resolved history, priors recomputed on it.
    prior_ns, prior_c = priors(past)
    final = make_model()
    final.fit([vector(r, prior_ns, prior_c) for r in labelled], [int(r["status"] == "no_show") for r in labelled])
    return {"model": final, "selected": selected, "prior_no_show": prior_ns, "prior_cancel": prior_c,
            "metrics": {"trained_on": len(labelled), "training_from": labelled[0]["reserved_for"][:10],
                        "training_to": labelled[-1]["reserved_for"][:10], "holdout_size": len(test_rows),
                        "holdout_no_shows": sum(y_test), "base_rate": round(no_shows / len(labelled), 4),
                        "model_brier": round(model_brier, 4), "baseline_brier": round(baseline_brier, 4),
                        "model_auc": None if auc is None else round(auc, 3),
                        "top_quartile_rate": None if top_rate is None else round(top_rate, 3),
                        "other_rate": None if rest_rate is None else round(rest_rate, 3)}}


def explain(row: dict, trained: dict, x: list[float]) -> list[dict]:
    """The factors that move this reservation's score most, as plain facts about the booking."""
    scaler, clf = trained["model"].named_steps["scaler"], trained["model"].named_steps["clf"]
    z = scaler.transform([x])[0]
    contribution = {name: float(z[i] * clf.coef_[0][i]) for i, name in enumerate(FEATURES)}
    when, resolved_before = row["when"], row["history"]
    lead_days = (when - row["made"]).total_seconds() / 86400
    facts = {
        "time": f"{when:%H:%M} {'dinner' if when.hour >= LUNCH_END_HOUR else 'lunch'} service",
        "weekday": DAY_NAMES[when.weekday()],
        "party": f"Party of {row['party_size']}",
        "lead": "Booked the same day" if lead_days < 1 else f"Booked {lead_days:.0f} days ahead",
        "phone": "Phone number given" if row["contact_phone"] else "No phone number",
        "notes": "Has notes" if (row["notes"] or "").strip() else "No notes",
        "history": ("First reservation" if resolved_before[0] == 0 else
                    f"{resolved_before[1]} no-show{'s' if resolved_before[1] != 1 else ''} in {resolved_before[0]} past visits"),
        "cancels": f"{resolved_before[3]} past cancellation{'s' if resolved_before[3] != 1 else ''}",
    }
    scored = sorted(((sum(contribution[name] for name in names), group) for group, names in GROUPS.items()),
                    key=lambda item: -abs(item[0]))
    return [{"factor": facts[group], "effect": "raises" if value > 0 else "lowers"}
            for value, group in scored[:3] if abs(value) >= 0.08]


def risk_level(probability: float) -> str:
    return "high" if probability >= HIGH_RISK else "medium" if probability >= MEDIUM_RISK else "low"


def predict(rows: list[dict], trained: dict, current: datetime, days: int) -> list[dict]:
    """Probabilities for confirmed reservations from now until the end of the last horizon day."""
    end = datetime.combine(current.date() + timedelta(days=days + 1), datetime.min.time())
    upcoming = [r for r in rows if r["status"] == "booked" and current <= r["when"] < end]
    if not upcoming:
        return []
    matrix = [vector(r, trained["prior_no_show"], trained["prior_cancel"]) for r in upcoming]
    if trained["selected"] == "LogisticRegression":
        scores = [float(p) for p in trained["model"].predict_proba(matrix)[:, 1]]
    else:
        scores = [trained["prior_no_show"]] * len(upcoming)
    results = []
    for row, x, score in zip(upcoming, matrix, scores):
        probability = min(0.999, max(0.001, score))
        results.append({
            "id": row["id"], "reserved_for": row["reserved_for"], "guest": row["full_name"],
            "party_size": row["party_size"], "table_label": row["table_label"],
            "probability": round(probability, 3),
            # Without a validated model nobody can be singled out: everyone gets the same average estimate.
            "risk": risk_level(probability) if trained["selected"] == "LogisticRegression" else "average",
            "channel": "sms" if row["contact_phone"] else "email",
            "factors": explain(row, trained, x) if trained["selected"] == "LogisticRegression" else [],
            "_row": row})
    return results


# --------------------------------------------------------------------------- overbooking

def no_show_distribution(probabilities: list[float]) -> list[float]:
    """Exact distribution of the number of no-shows (Poisson-binomial), assuming independent parties."""
    distribution = [1.0]
    for p in probabilities:
        following = [0.0] * (len(distribution) + 1)
        for count, mass in enumerate(distribution):
            following[count] += mass * (1 - p)
            following[count + 1] += mass * p
        distribution = following
    return distribution


def suggest_overbooking(probabilities: list[float]) -> dict:
    """Largest number k of extra bookings whose chance of exceeding capacity (fewer than k no-shows) stays low."""
    distribution = no_show_distribution(probabilities)
    expected = sum(probabilities)
    best = 0
    for extra in range(1, min(OVERBOOK_MAX, int(expected)) + 1):
        if sum(distribution[:extra]) <= OVERBOOK_TOLERANCE:
            best = extra
        else:
            break
    return {"expected_no_shows": round(expected, 2), "chance_of_any_no_show": round(1 - distribution[0], 3),
            "suggested_extra_bookings": best,
            "clash_risk": round(sum(distribution[:best]), 3) if best else 0.0}


def service_plans(predictions: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = {}
    for item in predictions:
        when = item["_row"]["when"]
        groups.setdefault((when.date().isoformat(), "lunch" if when.hour < LUNCH_END_HOUR else "dinner"), []).append(item)
    plans = []
    for (day, service), items in sorted(groups.items()):
        advice = suggest_overbooking([i["probability"] for i in items])
        plans.append({"date": day, "service": service, "bookings": len(items),
                      "covers": sum(i["party_size"] for i in items),
                      "covers_at_risk": round(sum(i["probability"] * i["party_size"] for i in items), 1), **advice})
    return plans


# --------------------------------------------------------------------------- reminders

def reminder_message(item: dict) -> str:
    when = item["_row"]["when"]
    first_name = (item["guest"] or "").split(" ")[0] or "there"
    return (f"Hello {first_name}, a reminder of your table for {item['party_size']} at {RESTAURANT_NAME} on "
            f"{when:%A %d %B} at {when:%H:%M}. If your plans have changed, please cancel from the Reservations "
            f"page so that we can offer the table to another guest. We look forward to welcoming you!")


def plan_reminders(predictions: list[dict], current: datetime) -> list[dict]:
    plan = []
    for item in predictions:
        if item["risk"] not in ("medium", "high"):
            continue
        when = item["_row"]["when"]
        previous = None
        for kind, lead in (("day_before", timedelta(hours=24)), ("same_day", timedelta(hours=3))):
            if kind == "same_day" and item["risk"] != "high":
                continue
            at = max(current, when - lead)
            if at > when - MIN_REMINDER_LEAD:
                continue
            if previous is not None and at - previous < timedelta(hours=6):
                continue   # two messages a few hours apart would only annoy the guest
            previous = at
            plan.append({"reservation_id": item["id"], "guest": item["guest"], "reserved_for": item["reserved_for"],
                         "kind": kind, "channel": item["channel"], "scheduled_for": at.strftime(TIME_FORMAT),
                         "risk": item["probability"], "message": reminder_message(item)})
    return plan


def reminder_rows(connection, ids: list[int]) -> dict[int, list[dict]]:
    found: dict[int, list[dict]] = {}
    if not ids:
        return found
    marks = ",".join("?" * len(ids))
    for r in connection.execute(
            f"SELECT reservation_id, kind, status, scheduled_for FROM reservation_reminders "
            f"WHERE reservation_id IN ({marks}) ORDER BY scheduled_for", ids):
        found.setdefault(r["reservation_id"], []).append(
            {"kind": r["kind"], "status": r["status"], "scheduled_for": r["scheduled_for"]})
    return found


def analyse(connection, days: int, current: datetime) -> tuple[dict, list[dict]]:
    rows = load_rows(connection, current)
    trained = train(rows, current)
    return trained, predict(rows, trained, current, days)


def overview(days: int = 7, current: datetime | None = None) -> dict:
    current = current or now()
    with get_connection() as connection:
        ensure_schema(connection)
        trained, predictions = analyse(connection, days, current)
        existing = reminder_rows(connection, [p["id"] for p in predictions])
    plan = plan_reminders(predictions, current)
    already = {(p["reservation_id"], p["kind"]) for p in plan
               if any(r["kind"] == p["kind"] for r in existing.get(p["reservation_id"], []))}
    for step in plan:
        step["already_scheduled"] = (step["reservation_id"], step["kind"]) in already
    services = service_plans(predictions)
    clean = []
    for item in predictions:
        clean.append({**{k: v for k, v in item.items() if k != "_row"}, "reminders": existing.get(item["id"], [])})
    metrics = trained["metrics"]
    notice = ("Probabilities are estimates from past reservations, not certainties. Overbooking and reminders are "
              "suggestions for staff: the booking engine still never double-books a table, and no reservation is "
              "changed automatically. Parties are assumed to behave independently.")
    if trained["selected"] != "LogisticRegression":
        notice = ("The classifier did not beat the plain restaurant-wide no-show rate on the latest reservations, so "
                  "that rate is used for everyone and no reservation stands out as at risk. " + notice)
    return {"model": trained["selected"], "candidate_model": "LogisticRegression", "horizon_days": days,
            "thresholds": {"medium": MEDIUM_RISK, "high": HIGH_RISK},
            "overbooking": {"tolerance": OVERBOOK_TOLERANCE, "max_extra": OVERBOOK_MAX},
            **metrics, "predictions": clean, "services": services, "reminder_plan": plan, "notice": notice}


def schedule_reminders(days: int = 7, current: datetime | None = None) -> dict:
    """Store the reminders of the current plan. Safe to repeat: one reminder per reservation and kind."""
    current = current or now()
    with get_connection() as connection:
        ensure_schema(connection)
        trained, predictions = analyse(connection, days, current)
        plan = plan_reminders(predictions, current)
        created = 0
        for step in plan:
            created += connection.execute(
                """INSERT OR IGNORE INTO reservation_reminders
                   (reservation_id, kind, channel, scheduled_for, message, risk, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (step["reservation_id"], step["kind"], step["channel"], step["scheduled_for"], step["message"],
                 step["risk"], current.strftime(TIME_FORMAT))).rowcount
    return {"model": trained["selected"], "planned": len(plan), "created": created, "already_scheduled": len(plan) - created}


def write_outbox(entry: dict) -> None:
    """Default delivery: append to a JSON-lines file that an SMS or e-mail gateway can pick up.

    The project has no messaging provider, so nothing leaves the machine from here.
    """
    OUTBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTBOX_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def dispatch_reminders(current: datetime | None = None, sender: Callable[[dict], None] | None = None) -> dict:
    """Hand every due reminder to the sender, skipping those whose reservation changed in the meantime."""
    current = current or now()
    sender = sender or write_outbox
    sent = skipped = failed = 0
    with get_connection() as connection:
        ensure_schema(connection)
        due = connection.execute(
            """SELECT rr.id, rr.reservation_id, rr.channel, rr.message, r.status AS reservation_status, r.reserved_for,
                      r.contact_phone, u.email
               FROM reservation_reminders rr JOIN reservations r ON r.id = rr.reservation_id
               JOIN users u ON u.id = r.user_id
               WHERE rr.status = 'pending' AND rr.scheduled_for <= ? ORDER BY rr.scheduled_for, rr.id""",
            (current.strftime(TIME_FORMAT),)).fetchall()
        for reminder in due:
            stamp = current.strftime(TIME_FORMAT)
            if reminder["reservation_status"] != "booked":
                connection.execute("UPDATE reservation_reminders SET status='skipped', detail=? WHERE id=?",
                                   ("The reservation is no longer confirmed.", reminder["id"]))
                skipped += 1
            elif datetime.fromisoformat(reminder["reserved_for"]) <= current + DISPATCH_CUTOFF:
                connection.execute("UPDATE reservation_reminders SET status='skipped', detail=? WHERE id=?",
                                   ("Too close to the reservation time.", reminder["id"]))
                skipped += 1
            else:
                destination = reminder["contact_phone"] if reminder["channel"] == "sms" else reminder["email"]
                try:
                    sender({"reminder_id": reminder["id"], "reservation_id": reminder["reservation_id"],
                            "channel": reminder["channel"], "to": destination, "message": reminder["message"],
                            "queued_at": stamp})
                except OSError as error:
                    connection.execute("UPDATE reservation_reminders SET detail=? WHERE id=?",
                                       (f"Delivery failed, will retry: {error}", reminder["id"]))
                    failed += 1
                    continue
                connection.execute("UPDATE reservation_reminders SET status='dispatched', dispatched_at=?, detail=? WHERE id=?",
                                   (stamp, "Handed to the outbox.", reminder["id"]))
                sent += 1
    return {"dispatched": sent, "skipped": skipped, "failed": failed, "delivery": "outbox",
            "notice": "No SMS or e-mail gateway is configured: dispatched reminders are appended to the outbox file "
                      "for a messaging service to deliver."}


def list_reminders(limit: int = 50) -> list[dict]:
    with get_connection() as connection:
        ensure_schema(connection)
        return [dict(r) for r in connection.execute(
            """SELECT rr.id, rr.reservation_id, rr.kind, rr.channel, rr.scheduled_for, rr.risk, rr.status, rr.detail,
                      rr.dispatched_at, r.reserved_for, u.full_name AS guest
               FROM reservation_reminders rr JOIN reservations r ON r.id = rr.reservation_id
               JOIN users u ON u.id = r.user_id ORDER BY rr.scheduled_for DESC, rr.id DESC LIMIT ?""", (limit,))]
