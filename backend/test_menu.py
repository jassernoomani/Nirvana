import sqlite3
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal environments
    from starlette.testclient import TestClient  # type: ignore[import-not-found]

from app import database
from app.main import app


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = database.DATABASE_PATH
        database.DATABASE_PATH = Path(self.temp.name) / "test.db"
        with sqlite3.connect(database.DATABASE_PATH) as connection:
            connection.execute("CREATE TABLE menu_items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT, price REAL NOT NULL CHECK(price > 0), category TEXT NOT NULL, is_available INTEGER NOT NULL DEFAULT 1)")
            connection.execute("INSERT INTO menu_items (name, price, category) VALUES ('Existing pizza', 12.5, 'Pizza')")
        connection.close()
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        database.DATABASE_PATH = self.original
        self.temp.cleanup()

    def test_migration_preserves_data_and_is_repeatable(self):
        database.initialize_database()
        row = self.client.get('/api/menu/1').json()
        self.assertEqual(row['name'], 'Existing pizza')
        self.assertEqual(row['preparation_minutes'], 15)
        self.assertFalse(row['is_vegetarian'])

    def test_create_filter_sort_page_patch_delete(self):
        result = self.client.post('/api/menu', json={'name': '  Salad  ', 'category': 'Starter', 'price': 7, 'is_vegetarian': True})
        self.assertEqual(result.status_code, 201)
        item = result.json()
        self.assertEqual(item['name'], 'Salad')
        rows = self.client.get('/api/menu', params={'search': 'sal', 'vegetarian': True, 'max_price': 8}).json()
        self.assertEqual([row['id'] for row in rows], [item['id']])
        rows = self.client.get('/api/menu', params={'sort': 'price', 'direction': 'desc', 'limit': 1}).json()
        self.assertEqual(rows[0]['id'], 1)
        page = self.client.get('/api/menu/page?page_size=1&page=2').json()
        self.assertEqual(page['total'], 2)
        self.assertEqual(len(page['items']), 1)
        self.assertEqual(self.client.get('/api/menu/categories').json(), ['Pizza', 'Starter'])
        updated = self.client.patch(f"/api/menu/{item['id']}", json={'is_available': False, 'description': None})
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json()['is_available'])
        self.assertEqual(updated.json()['price'], 7)
        self.assertEqual(self.client.delete(f"/api/menu/{item['id']}").status_code, 204)
        self.assertEqual(self.client.get(f"/api/menu/{item['id']}").status_code, 404)

    def test_invalid_input(self):
        for payload in [{'name': None}, {'price': 0}, {'name': '  '}, {'is_available': None}, {}, {'unknown': 1}, {'preparation_minutes': 241}]:
            self.assertEqual(self.client.patch('/api/menu/1', json=payload).status_code, 422, payload)
        self.assertEqual(self.client.get('/api/menu?sort=invalid').status_code, 422)
        self.assertEqual(self.client.get('/api/menu?min_price=20&max_price=10').status_code, 422)
        self.assertEqual(self.client.patch('/api/menu/999', json={'price': 10}).status_code, 404)

    def test_image_urls_and_partial_updates(self):
        image = '/assets/dishes/dish-1.webp'
        self.assertEqual(self.client.patch('/api/menu/1', json={'image_url': image}).status_code, 200)
        updated = self.client.patch('/api/menu/1', json={'price': 14}).json()
        self.assertEqual(updated['image_url'], image)
        self.assertEqual(self.client.get('/api/menu/page').json()['items'][0]['image_url'], image)
        self.assertEqual(self.client.patch('/api/menu/1', json={'image_url': 'javascript:alert(1)'}).status_code, 422)
        self.assertEqual(self.client.patch('/api/menu/1', json={'image_url': None}).json()['image_url'], None)


if __name__ == '__main__':
    unittest.main()
