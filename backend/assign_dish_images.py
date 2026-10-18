"""Assign locally prepared menu images without changing dish contents."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from app.database import DATABASE_PATH, initialize_database, get_connection

frontend = Path(__file__).resolve().parent.parent / 'frontend'
manifest = json.loads((frontend / 'dish-image-manifest.json').read_text())
for entry in manifest:
    if not (frontend / f"public/assets/dishes/dish-{entry['id']}.webp").is_file():
        raise RuntimeError(f"Missing image for {entry['name']}")
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
backup = DATABASE_PATH.with_name(f'restaurant.before-images-{stamp}.db')
source = sqlite3.connect(DATABASE_PATH)
target = sqlite3.connect(backup)
try:
    source.backup(target)
finally:
    target.close()
    source.close()
initialize_database()
with get_connection() as connection:
    for entry in manifest:
        connection.execute('UPDATE menu_items SET image_url = ? WHERE id = ?',
                           (f"/assets/dishes/dish-{entry['id']}.webp", entry['id']))
    # The two original Margherita records intentionally share the same image.
    connection.execute('UPDATE menu_items SET image_url = ? WHERE id = 2 AND name = ?',
                       ('/assets/dishes/dish-1.webp', 'Margherita Pizza'))
    rows = connection.execute('SELECT id, image_url FROM menu_items').fetchall()
    for row in rows:
        if not row['image_url'] or not (frontend / 'public' / row['image_url'].lstrip('/')).is_file():
            raise RuntimeError(f"Dish {row['id']} has no valid local image")
    print(f"Verified all {len(rows)} dishes have images.")
    print('Integrity:', connection.execute('PRAGMA integrity_check').fetchone()[0])
print('Backup:', backup)
