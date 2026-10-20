import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import seed_data
from app import database
from app.ai import llm, prompts
from app.main import app
from app.prep_time import MAX_MINUTES, ModelEstimate, fallback_minutes


class PrepTimeTests(unittest.TestCase):
    """The kitchen's AI preparation-time estimate: staff-only, real order data, safe fallback."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = database.DATABASE_PATH
        database.DATABASE_PATH = Path(self.temp.name) / 'prep.db'
        database.initialize_database()
        with database.get_connection() as c:
            seed_data.build(c, days=45)
            # The oldest open order: nothing is ahead of it in the kitchen.
            self.open_order = c.execute("SELECT id FROM orders WHERE status IN ('pending', 'preparing') "
                                        "ORDER BY created_at, id LIMIT 1").fetchone()['id']
            self.newest_order = c.execute("SELECT id FROM orders WHERE status IN ('pending', 'preparing') "
                                          "ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()['id']
            self.open_count = c.execute("SELECT COUNT(*) FROM orders WHERE status IN ('pending', 'preparing')").fetchone()[0]
            self.served_order = c.execute("SELECT id FROM orders WHERE status = 'served' LIMIT 1").fetchone()['id']
            self.dishes = sorted(r['name'] for r in c.execute(
                'SELECT m.name FROM order_items oi JOIN menu_items m ON m.id = oi.menu_item_id WHERE oi.order_id = ?', (self.open_order,)))
        self.context = TestClient(app)
        self.client = self.context.__enter__()

    def tearDown(self):
        self.context.__exit__(None, None, None)
        database.DATABASE_PATH = self.old
        self.temp.cleanup()

    def login(self, email):
        self.client.post('/api/auth/login', json={'email': email, 'password': seed_data.DEMO_PASSWORD})

    def url(self, order_id):
        return f'/api/kitchen/orders/{order_id}/estimate'

    def test_only_staff_can_ask_for_an_estimate(self):
        with patch('app.ai.llm.generate') as model:
            self.assertEqual(self.client.post(self.url(self.open_order)).status_code, 401)
            self.login('demo@nirvana.test')
            self.assertEqual(self.client.post(self.url(self.open_order)).status_code, 403)
        model.assert_not_called()

    def test_the_model_receives_the_real_dishes_and_queue(self):
        self.login('kitchen@nirvana.test')
        calls = []

        def fake(system, payload, schema):
            calls.append((system, payload))
            return ModelEstimate(extra_minutes=4, reason='Several portions of the same dish.')
        with patch('app.ai.llm.generate', side_effect=fake):
            response = self.client.post(self.url(self.open_order))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['source'], 'ai')
        system, payload = calls[0]
        # The code computes the base; the model only adds its extra minutes.
        self.assertEqual(response.json()['minutes'], payload['base_minutes'] + 4)
        self.assertEqual(system, prompts.PREP_TIME)
        self.assertEqual(sorted(item['name'] for item in payload['items']), self.dishes)
        self.assertTrue(all(item['prep_minutes'] > 0 and item['quantity'] > 0 for item in payload['items']))
        # The oldest open order has nothing ahead of it, and no customer data is sent.
        self.assertEqual(payload['orders_ahead'], 0)
        self.assertEqual(set(payload), {'items', 'orders_ahead', 'kitchen_staff', 'hour', 'base_minutes'})
        # The newest open order waits behind every other open one.
        with patch('app.ai.llm.generate', side_effect=fake):
            self.assertEqual(self.client.post(self.url(self.newest_order)).json()['orders_ahead'], self.open_count - 1)

    def test_a_model_failure_falls_back_to_the_formula(self):
        self.login('kitchen@nirvana.test')
        with patch('app.ai.llm.generate', side_effect=llm.ModelUnavailable('offline')):
            body = self.client.post(self.url(self.open_order)).json()
        self.assertEqual(body['source'], 'fallback')
        self.assertGreaterEqual(body['minutes'], 5)

    def test_the_model_cannot_add_more_than_30_minutes(self):
        with self.assertRaises(ValueError):
            ModelEstimate(extra_minutes=45, reason='Very long.')
        with patch('app.ai.llm.generate', return_value=ModelEstimate(extra_minutes=30, reason='Rush hour.')):
            from app.prep_time import estimate_prep_time
            long_queue = estimate_prep_time([{'name': 'Steak', 'prep_minutes': 25, 'quantity': 1}], queue=60, staff=1, hour=20)
        self.assertEqual(long_queue['minutes'], MAX_MINUTES)

    def test_unknown_and_finished_orders_are_refused(self):
        self.login('kitchen@nirvana.test')
        with patch('app.ai.llm.generate') as model:
            self.assertEqual(self.client.post(self.url(999999)).status_code, 404)
            self.assertEqual(self.client.post(self.url(self.served_order)).status_code, 409)
        model.assert_not_called()

    def test_fallback_formula(self):
        items = [{'name': 'Pizza', 'prep_minutes': 15, 'quantity': 2}, {'name': 'Lemonade', 'prep_minutes': 5, 'quantity': 1}]
        self.assertEqual(fallback_minutes(items, queue=4, staff=2), 18)  # 15 + 1.5 * 4 / 2
        self.assertEqual(fallback_minutes([], queue=0, staff=2), 10)
        self.assertEqual(fallback_minutes(items, queue=200, staff=1), MAX_MINUTES)


if __name__ == '__main__':
    unittest.main()
