"""Hourly order forecasting with chronological holdout; no LLM involved."""
import math
from collections import Counter
from datetime import datetime, timedelta
from statistics import mean

from fastapi import HTTPException
from app.database import get_connection

LAGS = (168, 336, 504)


def features(at, values):
    weekday, hour = at.weekday(), at.hour
    return [math.sin(2 * math.pi * hour / 24), math.cos(2 * math.pi * hour / 24),
            math.sin(2 * math.pi * weekday / 7), math.cos(2 * math.pi * weekday / 7),
            int(weekday >= 5), *[values.get(at - timedelta(hours=lag), 0) for lag in LAGS]]


def seasonal(at, values):
    return mean(values.get(at - timedelta(hours=lag), 0) for lag in LAGS)


def forecast(days=7, now=None):
    try:
        from sklearn.ensemble import RandomForestRegressor
    except ImportError as exc:
        raise HTTPException(503, 'Install the backend requirements to enable scikit-learn forecasting.') from exc
    now = now or datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_window = today - timedelta(days=120)
    with get_connection() as c:
        orders = c.execute("SELECT created_at FROM orders WHERE status!='cancelled' AND created_at>=? AND created_at<? ORDER BY created_at", (str(start_window), str(today))).fetchall()
        if not orders:
            raise HTTPException(422, 'At least 35 completed calendar days of order history are required.')
        first = datetime.fromisoformat(orders[0]['created_at']).replace(hour=0, minute=0, second=0, microsecond=0)
        # Skip the first recorded day, whose observation period may be incomplete.
        start = first + timedelta(days=1)
        if (today - start).days < 35:
            raise HTTPException(422, 'At least 35 completed calendar days of order history are required.')
        counts = Counter(datetime.fromisoformat(r['created_at']).replace(minute=0, second=0, microsecond=0) for r in orders)
        hours = [start + timedelta(hours=i) for i in range(int((today - start).total_seconds() / 3600))]
        observed = {at: counts[at] for at in hours}
        training = hours[504:]
        split = today - timedelta(days=7)
        train_hours = [at for at in training if at < split]
        test_hours = [at for at in training if at >= split]
        model = RandomForestRegressor(n_estimators=80, max_depth=10, min_samples_leaf=3, random_state=42, n_jobs=1)
        model.fit([features(at, observed) for at in train_hours], [observed[at] for at in train_hours])
        # Only observations before the holdout are visible. Weekly lags remain past-only.
        held_values = {at: value for at, value in observed.items() if at < split}
        predictions = model.predict([features(at, held_values) for at in test_hours])
        baseline = [seasonal(at, held_values) for at in test_hours]
        model_mae = mean(abs(float(prediction) - observed[at]) for at, prediction in zip(test_hours, predictions))
        baseline_mae = mean(abs(prediction - observed[at]) for at, prediction in zip(test_hours, baseline))
        selected = 'RandomForestRegressor' if model_mae <= baseline_mae else 'weekly-seasonal-baseline'
        model.fit([features(at, observed) for at in training], [observed[at] for at in training])
        # Predict today's hours as a bridge; publish the following full calendar days.
        future = dict(observed)
        hourly = []
        for i in range((days + 1) * 24):
            at = today + timedelta(hours=i)
            value = max(0, float(model.predict([features(at, future)])[0]) if selected == 'RandomForestRegressor' else seasonal(at, future))
            future[at] = value
            if at >= today + timedelta(days=1):
                hourly.append({'at': at.isoformat(timespec='minutes'), 'orders': round(value, 2)})
        daily = []
        for day in range(days):
            rows = hourly[day * 24:(day + 1) * 24]
            daily.append({'date': rows[0]['at'][:10], 'orders': round(sum(row['orders'] for row in rows), 1),
                          'peak_hour': max(rows, key=lambda row: row['orders'])['at'][11:16]})
        total_orders = sum(day['orders'] for day in daily)
        recent_start = today - timedelta(days=28)
        recent_order_count = c.execute("SELECT COUNT(*) FROM orders WHERE status!='cancelled' AND created_at>=? AND created_at<?", (str(recent_start), str(today))).fetchone()[0]
        usage = c.execute("""SELECT i.id,i.name,i.unit,i.stock_quantity,i.reorder_level,
            COALESCE(SUM(CASE WHEN o.id IS NOT NULL THEN oi.quantity*di.quantity ELSE 0 END),0) used
            FROM ingredients i LEFT JOIN dish_ingredients di ON di.ingredient_id=i.id
            LEFT JOIN order_items oi ON oi.menu_item_id=di.menu_item_id
            LEFT JOIN orders o ON o.id=oi.order_id AND o.status!='cancelled' AND o.created_at>=? AND o.created_at<?
            GROUP BY i.id""", (str(recent_start), str(today))).fetchall()
        ingredients = []
        for row in usage:
            amount = row['used'] / max(1, recent_order_count) * total_orders
            if row['unit'] == 'piece':
                amount = math.ceil(amount)
            shortage = max(0, amount + row['reorder_level'] - row['stock_quantity'])
            ingredients.append({'id': row['id'], 'name': row['name'], 'unit': row['unit'],
                'forecast_usage': round(amount, 1), 'stock': row['stock_quantity'], 'reserve': row['reorder_level'],
                'suggested_purchase': math.ceil(shortage) if row['unit'] == 'piece' else round(shortage, 1)})
        ingredients.sort(key=lambda item: (-bool(item['suggested_purchase']), item['name']))
    return {'model': selected, 'candidate_model': 'RandomForestRegressor', 'history_days': len(hours) // 24,
            'history_from': start.date().isoformat(), 'history_to': (today - timedelta(days=1)).date().isoformat(),
            'holdout_hours': len(test_hours), 'model_mae': round(model_mae, 3), 'baseline_mae': round(baseline_mae, 3),
            'total_orders': round(total_orders, 1), 'daily': daily, 'hourly': hourly, 'ingredients': ingredients,
            'notice': 'Estimates from recorded orders, not guarantees. Missing hours are assumed zero. Ingredient usage uses current recipes and the last 28 days of menu mix; purchasing suggestions include your reorder reserve. No stock or purchase orders are changed.'}
