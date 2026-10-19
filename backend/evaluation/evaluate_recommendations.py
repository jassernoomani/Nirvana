"""Safety audit and offline relevance test of the dish recommendations (app/ai/recommendations.py).

Run from backend:

    .venv/Scripts/python.exe evaluation/evaluate_recommendations.py          # rules only, no Ollama needed
    .venv/Scripts/python.exe evaluation/evaluate_recommendations.py --llm    # also the local-model re-ranking

1. Safety audit. Every recommendation is checked against an independent copy of the facts,
   taken from the seed's own source tables (seed_data.INGREDIENTS and MENU) rather than from
   the database queries the app uses: no dish with one of the customer's allergens, no meat
   or fish for a vegetarian, nothing unavailable or out of stock. It covers every seeded
   customer, plus a synthetic customer for every allergen and every pair of allergens, with
   and without the vegetarian flag.
2. Menu data audit. The filter is only as good as the recipes, so dish descriptions are
   searched for words that suggest an allergen the recipe does not record.
3. Relevance. Orders of the last 14 days are hidden; recommendations are built from the
   earlier history only and compared with the dishes each customer actually ordered in those
   14 days, against a popularity baseline and a random baseline under the same safety filter.

Results are printed and saved to evaluation/results/recommendations.json.
"""
import argparse
import itertools
import json
import random
import statistics
import sys
import tempfile
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND / ".env")

import seed_data  # noqa: E402
from app import database  # noqa: E402
from app.ai import llm  # noqa: E402
from app.ai.recommendations import recommend  # noqa: E402

RESULTS = Path(__file__).with_name("results")
NOW = datetime(2026, 10, 19, 12, 0)
HIDDEN_DAYS = 14
TOP = 6

# Independent facts, from the seed's source tables.
DISH_ALLERGENS = {dish[0]: {a for ingredient in dish[7] for a in seed_data.INGREDIENTS[ingredient][1]} for dish in seed_data.MENU}
DISH_HAS_MEAT = {dish[0]: bool(set(dish[7]) & seed_data.MEAT_OR_FISH) for dish in seed_data.MENU}
DISH_NAMES = {dish[0]: dish[1] for dish in seed_data.MENU}

# Words in a description that suggest an allergen (menu data audit).
HINTS = {"Dairy": ["cheese", "cream", "butter", "milk", "yogurt", "mozzarella", "parmesan", "ice cream"],
         "Gluten": ["bread", "pastry", "pasta", "pizza", "flour", "dough", "couscous", "crispy", "breaded", "batter"],
         "Eggs": ["egg", "mayonnaise", "aioli", "custard", "meringue", "pastry", "ice cream", "brownie"],
         "Nuts": ["walnut", "almond", "hazelnut", "pistachio", "pecan", "nut"],
         "Sesame": ["tahini", "sesame", "hummus"],
         "Fish": ["tuna", "sea bass", "anchov", "salmon", "fish"],
         "Shellfish": ["shrimp", "prawn", "crab", "lobster", "seafood"],
         "Molluscs": ["mussel", "calamari", "squid", "clam", "oyster", "seafood"],
         "Celery": ["celery", "broth", "stock"]}
SAUCE_WORDS = ["sauce", "dressing", "dip"]


def dish_recipe(dish_id):
    return next(dish[7] for dish in seed_data.MENU if dish[0] == dish_id)


def fresh_database(seed):
    folder = tempfile.TemporaryDirectory()
    database.DATABASE_PATH = Path(folder.name) / "recommendations.db"
    database.initialize_database()
    with database.get_connection() as connection:
        seed_data.build(connection, days=90, rng_seed=seed, now=NOW)
    return folder


def customers():
    with database.get_connection() as c:
        users = [dict(row) for row in c.execute("SELECT * FROM users WHERE role='customer' ORDER BY id")]
        allergies = {}
        for row in c.execute("SELECT ua.user_id, a.name FROM user_allergies ua JOIN allergens a ON a.id=ua.allergen_id"):
            allergies.setdefault(row[0], set()).add(row[1])
    for user in users:
        user["allergy_names"] = allergies.get(user["id"], set())
    return users


def in_stock(c, dish_id):
    rows = c.execute("SELECT di.quantity, i.stock_quantity FROM dish_ingredients di JOIN ingredients i ON i.id=di.ingredient_id "
                     "WHERE di.menu_item_id=?", (dish_id,)).fetchall()
    available = c.execute("SELECT is_available FROM menu_items WHERE id=?", (dish_id,)).fetchone()[0]
    return bool(rows) and available and all(r["stock_quantity"] >= r["quantity"] for r in rows)


def violations(user, items):
    """Every rule a recommendation list breaks, checked against the independent facts."""
    found = []
    with database.get_connection() as c:
        for item in items:
            dish_id = item["dish"]["id"]
            name = DISH_NAMES.get(dish_id, dish_id)
            if DISH_ALLERGENS[dish_id] & user["allergy_names"]:
                found.append(f"{name}: contains {sorted(DISH_ALLERGENS[dish_id] & user['allergy_names'])}")
            if user["is_vegetarian"] and DISH_HAS_MEAT[dish_id]:
                found.append(f"{name}: meat or fish for a vegetarian")
            if not in_stock(c, dish_id):
                found.append(f"{name}: unavailable or out of stock")
    return found


def synthetic_customers():
    """One customer for every allergen and every pair of allergens, with and without the vegetarian flag."""
    with database.get_connection() as c:
        allergen_ids = {row["name"]: row["id"] for row in c.execute("SELECT id, name FROM allergens")}
        profiles = [set(combo) for size in (1, 2) for combo in itertools.combinations(sorted(allergen_ids), size)]
        users = []
        for index, (allergies, vegetarian) in enumerate(itertools.product(profiles, [False, True])):
            user_id = c.execute("INSERT INTO users (email, full_name, password_hash, role, is_vegetarian, created_at) VALUES (?,?,?,?,?,?)",
                                (f"audit{index}@nirvana.test", f"Audit {index}", "-", "customer", int(vegetarian), NOW.strftime(database.TIME_FORMAT))).lastrowid
            c.executemany("INSERT INTO user_allergies VALUES (?, ?)", [(user_id, allergen_ids[a]) for a in allergies])
            users.append({"id": user_id, "is_vegetarian": int(vegetarian), "allergy_names": allergies})
    return users


def safety_audit(use_llm):
    real = customers()
    synthetic = synthetic_customers()
    result = {}
    for label, group in [("seeded customers", real), ("synthetic allergy profiles", synthetic)]:
        found, empty, shown = [], 0, 0
        for user in group:
            items = recommend(user)["items"]
            shown += len(items)
            empty += not items
            found += [f"user {user['id']}: {v}" for v in violations(user, items)]
        result[label] = {"customers": len(group), "dishes_shown": shown, "violations": found, "empty_lists": empty}
    if use_llm:
        found, fallbacks, shown, sample = [], 0, 0, real[:40]
        for user in sample:
            response = recommend(user, True)
            shown += len(response["items"])
            fallbacks += response["mode"] != "local-llm-reranked"
            found += [f"user {user['id']}: {v}" for v in violations(user, response["items"])]
        result["with local-model re-ranking"] = {"customers": len(sample), "dishes_shown": shown, "violations": found, "fallbacks": fallbacks}
    return result


def menu_data_audit():
    """Description words that suggest an allergen or an unlisted component the recipe does not record."""
    findings = []
    for dish_id, name, description, *_ in seed_data.MENU:
        text = f"{name} {description}".lower()
        for allergen, words in HINTS.items():
            hits = [w for w in words if w in text]
            if hits and allergen not in DISH_ALLERGENS[dish_id]:
                findings.append({"dish": name, "allergen": allergen, "words": hits})
        # Tomato sauce is a recorded ingredient; any other sauce or dressing has no recipe of its own.
        plain = text.replace("tomato and basil sauce", "")
        for ingredient in dish_recipe(dish_id):
            plain = plain.replace(ingredient.lower(), "")
        sauces = [w for w in SAUCE_WORDS if w in plain]
        if sauces:
            findings.append({"dish": name, "allergen": "unknown (sauce or dressing not broken down in the recipe)", "words": sauces})
    return findings


def hide_recent_orders():
    """Remove the last HIDDEN_DAYS of orders; return what each customer ordered in them, and in their next order."""
    cutoff = (NOW.replace(hour=0, minute=0, second=0) - timedelta(days=HIDDEN_DAYS)).strftime(database.TIME_FORMAT)
    with database.get_connection() as c:
        hidden, next_order, seen = {}, {}, {}
        for row in c.execute("SELECT o.id, o.user_id, oi.menu_item_id FROM orders o JOIN order_items oi ON oi.order_id=o.id "
                             "WHERE o.created_at>=? AND o.status!='cancelled' AND o.user_id IS NOT NULL ORDER BY o.created_at, o.id", (cutoff,)):
            hidden.setdefault(row[1], set()).add(row[2])
            if seen.setdefault(row[1], row[0]) == row[0]:
                next_order.setdefault(row[1], set()).add(row[2])
        c.execute("DELETE FROM orders WHERE created_at>=?", (cutoff,))
        past = Counter({row[0]: row[1] for row in c.execute("SELECT user_id, COUNT(*) FROM orders WHERE status!='cancelled' GROUP BY user_id")})
        popularity = Counter({row[0]: row[1] for row in c.execute(
            "SELECT oi.menu_item_id, SUM(oi.quantity) FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE o.status!='cancelled' GROUP BY oi.menu_item_id")})
    return hidden, next_order, past, popularity


def allowed(user, dish_id):
    with database.get_connection() as c:
        return not (DISH_ALLERGENS[dish_id] & user["allergy_names"]) and not (user["is_vegetarian"] and DISH_HAS_MEAT[dish_id]) and in_stock(c, dish_id)


def score_ranking(user, popularity_weight):
    """The app's score (recommendations.recommend) with an adjustable weight on overall popularity.

    With the app's weight (0.5) it must give exactly the app's list; relevance() checks this."""
    with database.get_connection() as c:
        favorites = {r[0] for r in c.execute("SELECT category FROM user_favorite_categories WHERE user_id=?", (user["id"],))}
        purchases = Counter({r[0]: r[1] for r in c.execute("SELECT oi.menu_item_id, SUM(oi.quantity) FROM order_items oi JOIN orders o ON o.id=oi.order_id "
                                                             "WHERE o.user_id=? AND o.status!='cancelled' GROUP BY oi.menu_item_id", (user["id"],))})
        popularity = Counter({r[0]: r[1] for r in c.execute("SELECT oi.menu_item_id, SUM(oi.quantity) FROM order_items oi JOIN orders o ON o.id=oi.order_id "
                                                              "WHERE o.status!='cancelled' GROUP BY oi.menu_item_id")})
        category = {r[0]: r[1] for r in c.execute("SELECT id, category FROM menu_items")}
    history = Counter()
    for dish_id, count in purchases.items():
        history[category[dish_id]] += count
    top = max(popularity.values(), default=1)
    def score(d):
        return ((5 if category[d] in favorites else 0) + min(3, purchases[d] * .8) + min(2, history[category[d]] * .12)
                + popularity_weight * popularity[d] / max(1, top))
    safe = [d for d in sorted(category) if allowed(user, d)]
    return sorted(safe, key=lambda d: (-round(score(d), 3), d))[:TOP]


POPULARITY_WEIGHTS = [0.5, 2, 4, 8]  # 0.5 is the app's


def relevance(seed, use_llm, rng):
    hidden, next_order, past, popularity = hide_recent_orders()
    users = [u for u in customers() if hidden.get(u["id"]) and past[u["id"]] >= 3]
    methods = {"app ranking": [], "popularity": [], "random": [], **{f"score, popularity weight {w}": [] for w in POPULARITY_WEIGHTS[1:]}}
    if use_llm:
        methods["app + local-model re-ranking"] = []
    for user in users:
        safe = [dish_id for dish_id in DISH_NAMES if allowed(user, dish_id)]
        lists = {"app ranking": [i["dish"]["id"] for i in recommend(user)["items"]],
                 "popularity": sorted(safe, key=lambda d: (-popularity[d], d))[:TOP],
                 "random": rng.sample(safe, min(TOP, len(safe))),
                 **{f"score, popularity weight {w}": score_ranking(user, w) for w in POPULARITY_WEIGHTS[1:]}}
        assert score_ranking(user, POPULARITY_WEIGHTS[0]) == lists["app ranking"], "the score copy no longer matches the app"
        if use_llm:
            response = recommend(user, True)
            lists["app + local-model re-ranking"] = [i["dish"]["id"] for i in response["items"]] if response["mode"] == "local-llm-reranked" else None
        for method, picks in lists.items():
            if picks is None:
                continue
            hits = set(picks) & hidden[user["id"]]
            next_hits = set(picks) & next_order[user["id"]]
            methods[method].append({"seed": seed, "user": user["id"], "hit": bool(hits), "precision": len(hits) / TOP,
                                    "recall": len(hits) / len(hidden[user["id"]]), "next_order_hit": bool(next_hits),
                                    "next_order_recall": len(next_hits) / len(next_order[user["id"]]), "picks": picks})
    return methods


def summarise(rows):
    distinct = {d for r in rows for d in r["picks"]}
    return {"customers": len(rows), "next_order_hit": round(statistics.mean(r["next_order_hit"] for r in rows), 3),
            "next_order_recall": round(statistics.mean(r["next_order_recall"] for r in rows), 3),
            "hit_rate": round(statistics.mean(r["hit"] for r in rows), 3),
            "precision_at_6": round(statistics.mean(r["precision"] for r in rows), 3),
            "recall_at_6": round(statistics.mean(r["recall"] for r in rows), 3),
            "distinct_dishes_recommended": len(distinct)}


def main():
    parser = argparse.ArgumentParser(description="Safety audit and relevance test of the recommendations.")
    parser.add_argument("--seeds", type=int, nargs="+", default=[2026, 1, 2])
    parser.add_argument("--llm", action="store_true", help="also test the local-model re-ranking (first seed only; needs Ollama)")
    args = parser.parse_args()
    rng = random.Random(42)

    safety, relevance_rows = {}, {}
    for index, seed in enumerate(args.seeds):
        use_llm = args.llm and index == 0
        folder = fresh_database(seed)
        safety[seed] = safety_audit(use_llm)
        for method, rows in relevance(seed, use_llm, rng).items():
            relevance_rows.setdefault(method, []).extend(rows)
        folder.cleanup()

    result = {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "seeds": args.seeds, "hidden_days": HIDDEN_DAYS, "top": TOP,
              "model": llm.settings()["model"] if args.llm else None, "safety": safety, "menu_data_audit": menu_data_audit(),
              "relevance": {method: summarise(rows) for method, rows in relevance_rows.items()}}
    if args.llm:
        # The re-ranking only ran on the first seed: compare it with the other methods on the same customers.
        result["relevance_first_seed"] = {method: summarise([r for r in rows if r["seed"] == args.seeds[0]]) for method, rows in relevance_rows.items()}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "recommendations.json").write_text(json.dumps(result, indent=2, default=list) + "\n", encoding="utf-8")

    print("Safety audit (violations / dishes shown):")
    for seed, groups in safety.items():
        for label, data in groups.items():
            extra = f", {data['empty_lists']} empty lists" if "empty_lists" in data else f", {data['fallbacks']} fallbacks to the rule ranking"
            print(f"  seed {seed:>4} {label:30} {len(data['violations'])} / {data['dishes_shown']} ({data['customers']} customers{extra})")
            for v in data["violations"][:5]:
                print(f"      {v}")
    print("\nMenu data audit:")
    for f in result["menu_data_audit"]:
        print(f"  {f['dish']:24} {f['allergen']:60} {f['words']}")
    print(f"\nRelevance: last {HIDDEN_DAYS} days hidden, top {TOP} compared with what was then ordered")
    print(f"{'method':32} {'customers':>9} {'next hit':>8} {'next rec':>8} {'14d hit':>8} {'precision':>9} {'recall':>7} {'distinct':>8}")
    for method, s in result["relevance"].items():
        print(f"{method:32} {s['customers']:>9} {s['next_order_hit']:>8.0%} {s['next_order_recall']:>8.2f} {s['hit_rate']:>8.0%} "
              f"{s['precision_at_6']:>9.2f} {s['recall_at_6']:>7.2f} {s['distinct_dishes_recommended']:>8}")
    if args.llm:
        print(f"\nSame customers as the re-ranking (seed {args.seeds[0]} only):")
        for method, s in result["relevance_first_seed"].items():
            print(f"{method:32} {s['customers']:>9} {s['next_order_hit']:>8.0%} {s['next_order_recall']:>8.2f} {s['hit_rate']:>8.0%} "
                  f"{s['precision_at_6']:>9.2f} {s['recall_at_6']:>7.2f} {s['distinct_dishes_recommended']:>8}")
    print("Saved evaluation/results/recommendations.json")


if __name__ == "__main__":
    main()
