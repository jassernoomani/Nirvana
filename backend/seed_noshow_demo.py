"""Add demo reservation history in which no-shows have realistic causes (optional).

seed_data.py draws every past outcome at random (7% no-shows whatever the booking), so no
classifier can learn anything from it and the no-show page honestly falls back to the base
rate. This script appends extra reservations to an already seeded database, in which a
no-show is more likely for large parties, weekend dinners, same-day bookings, bookings
without a phone number and a handful of customers who often fail to come. It also adds
confirmed bookings for the coming week so the page has something to score.

Rows added here have no table assigned (table_id is NULL); they never block a table in the
booking engine. Nothing else in the database is changed, and --remove deletes the reservations that have no table (these ones).

    python seed_noshow_demo.py            # add demo history
    python seed_noshow_demo.py --remove   # delete it again
"""
import argparse
import random
import sqlite3
import sys
from datetime import datetime, timedelta

from app import database

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
NOTES = ["Birthday dinner", "Window seat please", "High chair needed", "Anniversary", None, None, None, None]
LUNCH = ["12:00", "12:30", "13:00", "13:30"]
DINNER = ["19:00", "19:30", "20:00", "20:30", "21:00"]


def demo_rows(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT COUNT(*) FROM reservations WHERE table_id IS NULL").fetchone()[0]


def no_show_probability(when: datetime, party: int, lead_hours: float, has_phone: bool, habitual: bool) -> float:
    probability = 0.03
    if when.hour >= 16 and when.weekday() >= 5:
        probability += 0.12
    if party >= 6:
        probability += 0.10
    if lead_hours < 24:
        probability += 0.07
    if not has_phone:
        probability += 0.06
    if habitual:
        probability += 0.35
    return min(probability, 0.9)


def build(connection: sqlite3.Connection, days: int = 150, rng_seed: int = 7, now: datetime | None = None) -> dict:
    rng = random.Random(rng_seed)
    now = (now or datetime.now()).replace(microsecond=0)
    today = now.replace(hour=0, minute=0, second=0)
    customers = [r[0] for r in connection.execute("SELECT id FROM users WHERE role = 'customer' ORDER BY id")]
    if len(customers) < 20:
        raise ValueError("Run seed_data.py first: at least 20 customer accounts are needed.")
    habitual = set(rng.sample(customers, 10))
    weights = [3.0 if c in habitual else 1.0 for c in customers]
    rows = []

    def add(day, status_for):
        slot = rng.choice(LUNCH if rng.random() < 0.3 else DINNER)
        when = day + timedelta(hours=int(slot[:2]), minutes=int(slot[3:]))
        customer = rng.choices(customers, weights)[0]
        party = rng.choice([2, 2, 2, 3, 4, 4, 5, 6, 8])
        lead_hours = rng.choice([3, 6, 10, 20, 30, 48, 72, 120, 200])
        created = min(when - timedelta(hours=lead_hours), now)
        has_phone = rng.random() < (0.3 if customer in habitual else 0.7)
        phone = f"+216 {rng.randint(20, 99)} {rng.randint(100, 999)} {rng.randint(100, 999)}" if has_phone else None
        status = status_for(when, party, lead_hours, has_phone, customer in habitual)
        rows.append((customer, party, when.strftime(TIME_FORMAT), status, phone, rng.choice(NOTES), created.strftime(TIME_FORMAT)))

    def past_status(when, party, lead_hours, has_phone, is_habitual):
        if rng.random() < no_show_probability(when, party, lead_hours, has_phone, is_habitual):
            return "no_show"
        return "cancelled" if rng.random() < 0.06 else "completed"

    for day_index in range(-days, 0):
        for _ in range(rng.randint(3, 7)):
            add(today + timedelta(days=day_index), past_status)
    for day_index in range(0, 8):
        for _ in range(rng.randint(3, 6)):
            add(today + timedelta(days=day_index), lambda *_: "booked")
    # A booking earlier today than the current time would be a "booked" reservation in the past.
    rows = [r for r in rows if not (r[3] == "booked" and r[2] <= now.strftime(TIME_FORMAT))]
    connection.executemany(
        "INSERT INTO reservations (user_id, table_id, party_size, reserved_for, status, contact_phone, notes, created_at) "
        "VALUES (?, NULL, ?, ?, ?, ?, ?, ?)", rows)
    return {"added": len(rows), "past": sum(r[3] != "booked" for r in rows), "upcoming": sum(r[3] == "booked" for r in rows),
            "habitual_no_show_customers": len(habitual)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--remove", action="store_true", help="delete the demo reservations added by this script")
    args = parser.parse_args()
    if not database.DATABASE_PATH.exists():
        print(f"{database.DATABASE_PATH} not found. Run seed_data.py --reset first.")
        return 1
    database.initialize_database()
    with database.get_connection() as connection:
        existing = demo_rows(connection)
        if args.remove:
            connection.execute("DELETE FROM reservations WHERE table_id IS NULL")
            print(f"Removed {existing} demo reservations.")
            return 0
        if existing:
            print(f"{existing} reservations without a table already exist. Run with --remove first.")
            return 1
        try:
            summary = build(connection)
        except ValueError as error:
            print(error)
            return 1
    for name, count in summary.items():
        print(f"{name}: {count}")
    print("Open /admin/noshow as staff to see the predictions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
