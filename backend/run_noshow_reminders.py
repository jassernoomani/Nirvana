r"""Plan and send no-show reminders. Meant to run every 30 minutes from a scheduler.

Windows Task Scheduler (from the backend folder):
    .\.venv\Scripts\python.exe run_noshow_reminders.py

Linux / macOS cron:
    */30 * * * * cd /path/to/backend && .venv/bin/python run_noshow_reminders.py

It first stores reminders for medium and high risk reservations (never twice for the same
reservation), then hands every due reminder to the outbox file. Reservations that were
cancelled or are about to start are skipped.
"""
import argparse
import sys

from fastapi import HTTPException

from app import database
from app.ai import noshow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=7, choices=range(1, 15), metavar="1-14",
                        help="look at reservations in the next N days (default 7)")
    args = parser.parse_args()
    database.initialize_database()
    try:
        scheduled = noshow.schedule_reminders(args.days)
    except HTTPException as error:
        print(f"Not enough data to predict no-shows yet: {error.detail}")
        return 1
    sent = noshow.dispatch_reminders()
    print(f"Model: {scheduled['model']}")
    print(f"Planned: {scheduled['planned']} | newly stored: {scheduled['created']}")
    print(f"Dispatched: {sent['dispatched']} | skipped: {sent['skipped']} | failed: {sent['failed']}")
    print(sent["notice"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
