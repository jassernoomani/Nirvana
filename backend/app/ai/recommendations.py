from collections import Counter
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from app.database import get_connection
from app.ai import llm, prompts
from app.routers.menu import row_to_menu_item


class RankedIds(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dish_ids: list[StrictInt] = Field(max_length=6)


def recommend(user, use_llm=False):
    with get_connection() as c:
        allergies = [dict(row) for row in c.execute('SELECT a.id,a.name FROM user_allergies ua JOIN allergens a ON a.id=ua.allergen_id WHERE ua.user_id=?', (user['id'],))]
        favorites = [r[0] for r in c.execute('SELECT category FROM user_favorite_categories WHERE user_id=?', (user['id'],))]
        purchases = Counter({r['menu_item_id']: r['quantity'] for r in c.execute("SELECT oi.menu_item_id,SUM(oi.quantity) quantity FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE o.user_id=? AND o.status!='cancelled' GROUP BY oi.menu_item_id", (user['id'],))})
        popularity = Counter({r['menu_item_id']: r['quantity'] for r in c.execute("SELECT oi.menu_item_id,SUM(oi.quantity) quantity FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE o.status!='cancelled' GROUP BY oi.menu_item_id")})
        history_categories = Counter()
        candidates = []
        menu = c.execute('SELECT * FROM menu_items').fetchall()
        for dish in menu:
            history_categories[dish['category']] += purchases[dish['id']]
        allergy_ids = {a['id'] for a in allergies}
        excluded = 0
        for row in menu:
            recipe = c.execute('SELECT di.ingredient_id,di.quantity,i.stock_quantity FROM dish_ingredients di JOIN ingredients i ON i.id=di.ingredient_id WHERE di.menu_item_id=?', (row['id'],)).fetchall()
            allergen_rows = c.execute('SELECT DISTINCT a.id,a.name FROM dish_ingredients di JOIN ingredient_allergens ia ON ia.ingredient_id=di.ingredient_id JOIN allergens a ON a.id=ia.allergen_id WHERE di.menu_item_id=?', (row['id'],)).fetchall()
            if (not row['is_available'] or not recipe or any(r['stock_quantity'] < r['quantity'] for r in recipe)
                or (user['is_vegetarian'] and not row['is_vegetarian']) or allergy_ids.intersection(r['id'] for r in allergen_rows)):
                excluded += 1
                continue
            reasons = []
            if row['category'] in favorites:
                reasons.append('Matches a favorite category')
            if purchases[row['id']]:
                reasons.append('A dish you have ordered before')
            elif history_categories[row['category']]:
                reasons.append('Similar to categories in your order history')
            if not reasons:
                reasons.append('Popular with restaurant customers' if popularity[row['id']] else 'An available dish to discover')
            score = (5 if row['category'] in favorites else 0) + min(3, purchases[row['id']] * .8) + min(2, history_categories[row['category']] * .12) + .5 * popularity[row['id']] / max(1, max(popularity.values(), default=1))
            candidates.append({'dish': row_to_menu_item(row), 'score': round(score, 3), 'reasons': reasons,
                               'allergens': [r['name'] for r in allergen_rows]})
    candidates.sort(key=lambda item: (-item['score'], item['dish']['id']))
    shortlist = candidates[:12]
    result = shortlist[:6]
    mode, warning = 'history-and-preferences', None
    if use_llm and shortlist:
        try:
            response = llm.generate(prompts.RECOMMENDATIONS, {'candidates': [{'id': item['dish']['id'], 'name': item['dish']['name'], 'category': item['dish']['category'], 'evidence': item['reasons']} for item in shortlist]}, RankedIds)
            ids = response.dish_ids
            lookup = {item['dish']['id']: item for item in shortlist}
            if not ids or len(ids) != len(set(ids)) or any(id not in lookup for id in ids):
                raise llm.LocalModelError('Model ranking contained unknown or duplicate dish IDs.')
            result = [lookup[id] for id in ids]
            mode = 'local-llm-reranked'
        except llm.LocalModelError as exc:
            warning = str(exc) + ' Showing the history-based ranking instead.'
    return {'items': result, 'mode': mode, 'model': llm.settings()['model'] if mode == 'local-llm-reranked' else None,
            'warning': warning, 'excluded_count': excluded,
            'profile': {'is_vegetarian': user['is_vegetarian'], 'allergies': [a['name'] for a in allergies], 'favorite_categories': favorites, 'history_items': sum(purchases.values())},
            'notice': 'Filtered against recorded recipes and allergies only. Ask staff about cross-contact and ingredient changes.'}
