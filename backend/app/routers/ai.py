from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from app.auth import current_user, require_customer, require_staff
from app.database import get_connection
from app.ai import llm, prompts
from app.ai.recommendations import recommend
from app.ai.forecast import forecast
from app.ai.reviews import analyze

router = APIRouter(prefix='/api/ai', tags=['Restaurant intelligence'])


class Preferences(BaseModel):
    model_config = ConfigDict(extra='forbid')
    is_vegetarian: bool
    allergen_ids: list[int] = Field(max_length=40)
    favorite_categories: list[str] = Field(max_length=30)


@router.get('/status')
def model_status(user=Depends(current_user)):
    return llm.status()


@router.get('/profile')
def profile(user=Depends(require_customer)):
    with get_connection() as c:
        return {'is_vegetarian': user['is_vegetarian'],
                'allergens': [dict(r) for r in c.execute('SELECT * FROM allergens ORDER BY name')],
                'allergen_ids': [r[0] for r in c.execute('SELECT allergen_id FROM user_allergies WHERE user_id=?', (user['id'],))],
                'categories': [r[0] for r in c.execute('SELECT DISTINCT category FROM menu_items ORDER BY category')],
                'favorite_categories': [r[0] for r in c.execute('SELECT category FROM user_favorite_categories WHERE user_id=?', (user['id'],))]}


@router.put('/profile')
def save_preferences(body: Preferences, user=Depends(require_customer)):
    with get_connection() as c:
        allergens = {r[0] for r in c.execute('SELECT id FROM allergens')}
        categories = {r[0] for r in c.execute('SELECT DISTINCT category FROM menu_items')}
        if not set(body.allergen_ids) <= allergens or not set(body.favorite_categories) <= categories:
            raise HTTPException(422, 'Unknown allergen or category')
        c.execute('UPDATE users SET is_vegetarian=? WHERE id=?', (int(body.is_vegetarian), user['id']))
        c.execute('DELETE FROM user_allergies WHERE user_id=?', (user['id'],))
        c.execute('DELETE FROM user_favorite_categories WHERE user_id=?', (user['id'],))
        c.executemany('INSERT INTO user_allergies (user_id,allergen_id) VALUES (?,?)', [(user['id'], id) for id in set(body.allergen_ids)])
        c.executemany('INSERT INTO user_favorite_categories (user_id,category) VALUES (?,?)', [(user['id'], category) for category in set(body.favorite_categories)])
    return {'saved': True}


@router.get('/recommendations')
def recommendations(use_llm: bool = False, user=Depends(require_customer)):
    return recommend(user, use_llm)


@router.get('/forecast')
def demand_forecast(days: int = Query(default=7, ge=1, le=14), user=Depends(require_staff)):
    return forecast(days)


@router.post('/reviews')
def review_analysis(days: int = Query(default=30, ge=1, le=120), limit: int = Query(default=8, ge=1, le=48), user=Depends(require_staff)):
    return analyze(days, limit)


@router.get('/prompts')
def exact_prompts(user=Depends(require_staff)):
    return {'version': prompts.PROMPT_VERSION, 'recommendations': prompts.RECOMMENDATIONS,
            'review_classification': prompts.REVIEW_CLASSIFICATION, 'review_summary': prompts.REVIEW_SUMMARY}
