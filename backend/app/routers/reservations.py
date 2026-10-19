import os
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status  # type: ignore

from app.auth import require_customer
from app.database import get_connection
from app.schemas import Availability, Reservation, ReservationRequest

router = APIRouter(prefix="/api/reservations", tags=["Reservations"])

# Booking rules. The project does not define them, so these defaults follow the
# demo data (two-hour seatings, lunch and dinner services) and can be changed
# with environment variables without touching the code.
SEATING_MINUTES = int(os.getenv("RESERVATION_SEATING_MINUTES", "120"))
SLOT_INTERVAL_MINUTES = int(os.getenv("RESERVATION_SLOT_INTERVAL_MINUTES", "30"))
# First and last seating time of each service, "HH:MM-HH:MM", comma separated.
SERVICES = os.getenv("RESERVATION_SERVICES", "12:00-14:00,19:00-21:00")
MIN_NOTICE_MINUTES = int(os.getenv("RESERVATION_MIN_NOTICE_MINUTES", "60"))
MAX_DAYS_AHEAD = int(os.getenv("RESERVATION_MAX_DAYS_AHEAD", "60"))

# Statuses that keep a table occupied. "booked" is shown to customers as Confirmed.
ACTIVE = ("booked", "seated")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def slot_times() -> list[str]:
    times = []
    for service in SERVICES.split(","):
        first, last = (datetime.strptime(part.strip(), "%H:%M") for part in service.split("-"))
        while first <= last:
            times.append(first.strftime("%H:%M"))
            first += timedelta(minutes=SLOT_INTERVAL_MINUTES)
    return times


def now() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


def free_table(connection, start: datetime, party_size: int):
    """The smallest table that seats the party and has no active booking overlapping the seating."""
    return connection.execute(
        f"""SELECT id, label FROM restaurant_tables t WHERE seats >= ? AND NOT EXISTS (
                SELECT 1 FROM reservations r WHERE r.table_id = t.id AND r.status IN {ACTIVE}
                AND ABS(strftime('%s', r.reserved_for) - strftime('%s', ?)) < ?)
            ORDER BY seats, id LIMIT 1""",
        (party_size, start.strftime(TIME_FORMAT), SEATING_MINUTES * 60)).fetchone()


def max_party_size(connection) -> int:
    return connection.execute("SELECT COALESCE(MAX(seats), 0) FROM restaurant_tables").fetchone()[0]


def check_request(day: date, time: str, party_size: int, largest: int) -> datetime:
    if time not in slot_times():
        raise HTTPException(422, f"Choose one of our seating times: {', '.join(slot_times())}")
    start = datetime.combine(day, datetime.strptime(time, "%H:%M").time())
    if start <= now():
        raise HTTPException(422, "Choose a date and time in the future")
    if start < now() + timedelta(minutes=MIN_NOTICE_MINUTES):
        raise HTTPException(422, f"Reservations must be made at least {MIN_NOTICE_MINUTES} minutes in advance")
    if day > now().date() + timedelta(days=MAX_DAYS_AHEAD):
        raise HTTPException(422, f"Reservations open {MAX_DAYS_AHEAD} days in advance")
    if party_size > largest:
        raise HTTPException(422, f"Online bookings are for up to {largest} guests. For larger groups, please contact the restaurant")
    return start


def load(connection, where: str, parameters: tuple) -> list[dict]:
    return [dict(row) for row in connection.execute(
        f"""SELECT r.id, r.reserved_for, r.party_size, r.status, t.label AS table_label, r.contact_phone, r.notes, r.created_at
            FROM reservations r LEFT JOIN restaurant_tables t ON t.id = r.table_id
            WHERE {where} ORDER BY r.reserved_for DESC, r.id DESC""", parameters)]


@router.get("/availability", response_model=Availability)
def availability(day: date = Query(alias="date"), party_size: int = Query(ge=1, le=20)):
    """Public: which seating times have a free table for this party size."""
    with get_connection() as connection:
        largest = max_party_size(connection)
        slots = []
        for time in slot_times():
            start = datetime.combine(day, datetime.strptime(time, "%H:%M").time())
            bookable = (party_size <= largest and start >= now() + timedelta(minutes=MIN_NOTICE_MINUTES)
                        and day <= now().date() + timedelta(days=MAX_DAYS_AHEAD))
            slots.append({"time": time, "available": bool(bookable and free_table(connection, start, party_size))})
    return {"date": day, "party_size": party_size, "duration_minutes": SEATING_MINUTES,
            "max_party_size": largest, "slots": slots}


@router.post("", response_model=Reservation, status_code=status.HTTP_201_CREATED)
def book(body: ReservationRequest, user: dict = Depends(require_customer)):
    with get_connection() as connection:
        # Take the write lock first so two people cannot be given the same table.
        connection.execute("BEGIN IMMEDIATE")
        start = check_request(body.date, body.time, body.party_size, max_party_size(connection))
        clash = connection.execute(
            f"""SELECT 1 FROM reservations WHERE user_id = ? AND status IN {ACTIVE}
                AND ABS(strftime('%s', reserved_for) - strftime('%s', ?)) < ?""",
            (user["id"], start.strftime(TIME_FORMAT), SEATING_MINUTES * 60)).fetchone()
        if clash:
            raise HTTPException(409, "You already have a reservation around this time")
        table = free_table(connection, start, body.party_size)
        if table is None:
            raise HTTPException(409, f"No table for {body.party_size} is free at {body.time} on "
                                     f"{body.date:%d %B %Y}. Please choose another time")
        reservation_id = connection.execute(
            "INSERT INTO reservations (user_id, table_id, party_size, reserved_for, status, contact_phone, notes, created_at) "
            "VALUES (?, ?, ?, ?, 'booked', ?, ?, ?)",
            (user["id"], table["id"], body.party_size, start.strftime(TIME_FORMAT), body.contact_phone, body.notes,
             now().strftime(TIME_FORMAT))).lastrowid
        return load(connection, "r.id = ?", (reservation_id,))[0]


@router.get("", response_model=list[Reservation])
def my_reservations(user: dict = Depends(require_customer)):
    with get_connection() as connection:
        return load(connection, "r.user_id = ?", (user["id"],))


@router.post("/{reservation_id}/cancel", response_model=Reservation)
def cancel(reservation_id: int, user: dict = Depends(require_customer)):
    with get_connection() as connection:
        # Someone else's reservation looks exactly like one that does not exist.
        found = load(connection, "r.id = ? AND r.user_id = ?", (reservation_id, user["id"]))
        if not found:
            raise HTTPException(404, "Reservation not found")
        reservation = found[0]
        if reservation["status"] != "booked":
            raise HTTPException(409, "Only confirmed reservations can be cancelled")
        if reservation["reserved_for"] <= now().strftime(TIME_FORMAT):
            raise HTTPException(409, "This reservation has already started")
        connection.execute("UPDATE reservations SET status = 'cancelled' WHERE id = ?", (reservation_id,))
        return load(connection, "r.id = ?", (reservation_id,))[0]
