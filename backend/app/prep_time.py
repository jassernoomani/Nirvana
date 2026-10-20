"""AI estimate of how long an open order still needs in the kitchen (contributed by Skander Ferjani).

Runs on the same local model as the other AI modules (app.ai.llm), so no order data leaves the PC
and no API key is needed. The model only refines what the code can already compute: its answer is
bounded, and any failure falls back to the standard formula, so the kitchen always gets a number.
"""
import os

from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.ai import llm, prompts
from app.database import get_connection

MIN_MINUTES, MAX_MINUTES = 5, 90


class ModelEstimate(BaseModel):
    """What the model must return; enforced while it writes, then validated.

    The model only adds minutes to the formula: a small model sums dish times instead of treating
    them as cooked in parallel (it answered 43 minutes for a 30-minute dish with no queue), so the
    arithmetic stays in code and the model judges what the formula ignores."""
    model_config = ConfigDict(extra='forbid')
    extra_minutes: StrictInt = Field(ge=0, le=30)
    reason: str = Field(min_length=1, max_length=200)


class OrderNotFound(LookupError):
    pass


class OrderNotOpen(ValueError):
    pass


def kitchen_staff() -> int:
    """Cooks on shift: not tracked in the database, so set in .env (KITCHEN_STAFF), 2 by default."""
    try:
        return max(1, int(os.getenv('KITCHEN_STAFF', '2')))
    except ValueError:
        return 2


def bounded(minutes: float) -> int:
    return max(MIN_MINUTES, min(round(minutes), MAX_MINUTES))


def fallback_minutes(items, queue, staff):
    longest = max((i["prep_minutes"] for i in items), default=10)
    return bounded(longest + 1.5 * queue / max(staff, 1))


def estimate_prep_time(items, queue, staff, hour):
    """items: [{"name", "prep_minutes", "quantity"}]; queue: open orders ahead; staff: cooks; hour: 0-23."""
    base = fallback_minutes(items, queue, staff)
    payload = {'items': items, 'orders_ahead': queue, 'kitchen_staff': staff, 'hour': hour, 'base_minutes': base}
    try:
        result = llm.generate(prompts.PREP_TIME, payload, ModelEstimate)
        return {'minutes': bounded(base + result.extra_minutes), 'reason': result.reason, 'source': 'ai'}
    except llm.LocalModelError:
        return {'minutes': base,
                'reason': 'Standard estimate: the slowest dish plus the orders ahead, shared between the cooks.',
                'source': 'fallback'}


def estimate_for_order(order_id: int) -> dict:
    """Reads the order's real dishes and the queue ahead of it, then estimates."""
    with get_connection() as connection:
        order = connection.execute('SELECT id, status, created_at FROM orders WHERE id = ?', (order_id,)).fetchone()
        if order is None:
            raise OrderNotFound('Order not found')
        if order['status'] not in ('pending', 'preparing'):
            raise OrderNotOpen(f"This order is already {order['status']}: estimates are for new or preparing orders")
        items = [{'name': row['name'], 'prep_minutes': row['preparation_minutes'], 'quantity': row['quantity']}
                 for row in connection.execute(
                     'SELECT m.name, m.preparation_minutes, oi.quantity FROM order_items oi '
                     'JOIN menu_items m ON m.id = oi.menu_item_id WHERE oi.order_id = ? ORDER BY m.name', (order_id,))]
        # Orders the kitchen will work on first: open ones placed earlier.
        queue = connection.execute(
            "SELECT COUNT(*) FROM orders WHERE status IN ('pending', 'preparing') AND id != ? "
            "AND (created_at < ? OR (created_at = ? AND id < ?))",
            (order_id, order['created_at'], order['created_at'], order_id)).fetchone()[0]
    estimate = estimate_prep_time(items, queue, kitchen_staff(), int(order['created_at'][11:13]))
    return {**estimate, 'orders_ahead': queue}
