from app.prep_time import estimate_prep_time

menu = {
    "pizza": {"name": "Pizza", "prep_minutes": 15},
    "pasta": {"name": "Pasta", "prep_minutes": 12},
    "salad": {"name": "Caesar Salad", "prep_minutes": 5},
    "cola": {"name": "Cola", "prep_minutes": 1},
    "steak": {"name": "Grilled Steak", "prep_minutes": 20},
    "soup": {"name": "Tomato Soup", "prep_minutes": 8},
    "tiramisu": {"name": "Tiramisu", "prep_minutes": 3},
    "burger": {"name": "Burger", "prep_minutes": 14},
}

scenarios = [
    ("Single drink, empty kitchen",
     [menu["cola"]], 0, 3, 15),
    ("One pizza, quiet kitchen",
     [menu["pizza"]], 1, 3, 15),
    ("Full meal for one, normal load",
     [menu["soup"], menu["steak"], menu["tiramisu"], menu["cola"]], 4, 2, 19),
    ("Large family order, normal load",
     [menu["pizza"], menu["pizza"], menu["pasta"], menu["pasta"],
      menu["salad"], menu["cola"], menu["cola"], menu["cola"]], 4, 2, 13),
    ("Same family order, rush hour, short staff",
     [menu["pizza"], menu["pizza"], menu["pasta"], menu["pasta"],
      menu["salad"], menu["cola"], menu["cola"], menu["cola"]], 12, 1, 20),
    ("Burger, very busy kitchen",
     [menu["burger"]], 15, 2, 20),
    ("Empty order (edge case)",
     [], 3, 2, 12),
]

for title, items, queue, staff, hour in scenarios:
    result = estimate_prep_time(items, queue=queue, staff=staff, hour=hour)
    print(f"{title}")
    print(f"  items={len(items)} queue={queue} staff={staff} hour={hour}")
    print(f"  -> {result['minutes']} min ({result['source']}): {result['reason']}\n")