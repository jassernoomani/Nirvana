from fastapi import APIRouter, Depends, Query  # type: ignore

from app.ai import noshow
from app.auth import require_staff

router = APIRouter(prefix="/api/ai/noshow", tags=["No-show prediction"])


@router.get("/overview")
def overview(days: int = Query(default=7, ge=1, le=14), user: dict = Depends(require_staff)):
    """Risk per upcoming reservation, overbooking advice per service and the reminder plan."""
    return noshow.overview(days)


@router.post("/reminders/schedule")
def schedule(days: int = Query(default=7, ge=1, le=14), user: dict = Depends(require_staff)):
    """Store reminders for medium and high risk reservations. Repeating it creates no duplicates."""
    return noshow.schedule_reminders(days)


@router.post("/reminders/dispatch")
def dispatch(user: dict = Depends(require_staff)):
    """Hand every due reminder to the outbox, skipping reservations that changed in the meantime."""
    return noshow.dispatch_reminders()


@router.get("/reminders")
def reminders(limit: int = Query(default=50, ge=1, le=200), user: dict = Depends(require_staff)):
    return noshow.list_reminders(limit)
