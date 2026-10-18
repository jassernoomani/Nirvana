"""Add sample dishes without replacing existing records. Run from backend."""

from datetime import datetime, timezone
import sqlite3

from app.database import DATABASE_PATH, get_connection, initialize_database
from app.schemas import MenuItemCreate


# Sample prices use the same unspecified currency as the current menu.
# Vegetarian values describe these recipes; ingredient sourcing must be verified.
DISHES = [
    ("Bruschetta", "Toasted bread with ripe tomatoes, basil, garlic, and olive oil", 6.5, "Starters", 10, True),
    ("Roasted Tomato Soup", "Slow-roasted tomatoes blended with basil and served with toasted bread", 7.0, "Starters", 12, True),
    ("Crispy Calamari", "Golden calamari rings with lemon and garlic dipping sauce", 9.5, "Starters", 15, False),
    ("Hummus and Flatbread", "Chickpea hummus with tahini, olive oil, and warm flatbread", 6.0, "Starters", 8, True),
    ("Mediterranean Salad", "Cucumber, tomatoes, olives, red onion, and lemon dressing", 8.5, "Salads", 10, True),
    ("Grilled Chicken Salad", "Grilled chicken, mixed greens, cherry tomatoes, and herb dressing", 11.5, "Salads", 18, False),
    ("Quinoa Garden Bowl", "Quinoa, roasted vegetables, chickpeas, and a lemon-tahini dressing", 10.0, "Salads", 15, True),
    ("Pepperoni Pizza", "Tomato sauce, mozzarella, and pepperoni on a crisp pizza base", 15.0, "Pizza", 20, False),
    ("Garden Vegetable Pizza", "Tomato sauce, peppers, mushrooms, zucchini, and olives", 14.0, "Pizza", 20, True),
    ("Tuna and Olive Pizza", "Tomato sauce, mozzarella, tuna, red onion, and black olives", 16.0, "Pizza", 22, False),
    ("Penne Arrabbiata", "Penne in a spicy tomato sauce with garlic, chili, and parsley", 12.0, "pasta", 18, True),
    ("Mushroom Tagliatelle", "Tagliatelle with sauteed mushrooms, cream, and thyme", 15.5, "pasta", 22, True),
    ("Spaghetti Bolognese", "Spaghetti with slow-cooked beef and tomato sauce", 16.5, "pasta", 20, False),
    ("Seafood Linguine", "Linguine with shrimp, mussels, tomato, and garlic", 21.0, "pasta", 25, False),
    ("Grilled Sea Bass", "Grilled sea bass with lemon, seasonal vegetables, and roasted potatoes", 25.0, "Mains", 30, False),
    ("Herb-Roasted Chicken", "Roasted chicken with rosemary, garlic, and potato wedges", 19.0, "Mains", 30, False),
    ("Beef Steak and Fries", "Grilled beef steak with fries and a pepper sauce", 28.0, "Mains", 25, False),
    ("Vegetable Couscous", "Steamed couscous with carrots, zucchini, chickpeas, and vegetable broth", 14.5, "Mains", 25, True),
    ("Chocolate Brownie", "Warm chocolate brownie with vanilla ice cream", 7.5, "Desserts", 10, True),
    ("Lemon Tart", "Crisp pastry filled with lemon cream and topped with citrus zest", 6.5, "Desserts", 8, True),
    ("Seasonal Fruit Salad", "A fresh selection of seasonal fruit with mint", 5.5, "Desserts", 7, True),
    ("Fresh Lemonade", "Freshly squeezed lemon juice with water and a touch of sugar", 4.5, "Drinks", 5, True),
    ("Mint Tea", "Hot green tea infused with fresh mint", 3.0, "Drinks", 5, True),
    ("Orange Juice", "Freshly squeezed orange juice", 5.0, "Drinks", 5, True),
]


def seed_menu():
    backup_path = None
    if DATABASE_PATH.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = DATABASE_PATH.with_name(f"restaurant.before-seed-{stamp}.db")
        source = sqlite3.connect(DATABASE_PATH)
        target = sqlite3.connect(backup_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()

    initialize_database()
    added = 0
    with get_connection() as connection:
        for name, description, price, category, minutes, vegetarian in DISHES:
            dish = MenuItemCreate(name=name, description=description, price=price, category=category,
                                  preparation_minutes=minutes, is_vegetarian=vegetarian)
            exists = connection.execute(
                "SELECT id FROM menu_items WHERE lower(trim(name)) = lower(?) AND lower(trim(category)) = lower(?)",
                (dish.name, dish.category),
            ).fetchone()
            if exists:
                continue
            connection.execute(
                "INSERT INTO menu_items (name, description, price, category, is_available, preparation_minutes, is_vegetarian) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (dish.name, dish.description, dish.price, dish.category, int(dish.is_available),
                 dish.preparation_minutes, int(dish.is_vegetarian)),
            )
            added += 1
        print(f"Added {added} dishes. Existing dishes were preserved.")
        for row in connection.execute("SELECT category, count(*) AS count FROM menu_items GROUP BY category ORDER BY category"):
            print(f"{row['category']}: {row['count']}")
        print(f"Database integrity: {connection.execute('PRAGMA integrity_check').fetchone()[0]}")
    if backup_path:
        print(f"Backup: {backup_path}")


if __name__ == "__main__":
    seed_menu()
