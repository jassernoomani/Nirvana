# Nirvana: the three intelligence modules

Implementation lives in this Git checkout, `.publish-nirvana`. The original sibling backend/frontend directories are an older version. No cloud API key is required and nothing is pushed automatically.

## Where to use them

| Module | Page | Access |
|---|---|---|
| Dish recommendations | `/recommendations` (Picked for you in the customer header) | Customer |
| Demand and ingredient forecast | `/admin/intelligence` | Staff |
| Review analysis and exact prompts | `/admin/intelligence`, corresponding tabs | Staff |

Demo customer: `demo@nirvana.test`. Demo staff: `manager@nirvana.test`. Both use the existing demo password `nirvana-demo`.

## Local model configuration

Ollama was detected at `http://127.0.0.1:11434` with `qwen2.5:3b`, selected by the user. This is Qwen, not a Llama-family model. The Ollama adapter also works with an installed Llama model by changing its exact tag.

`backend/.env` (ignored by Git) is loaded on backend startup:

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
LLM_MODEL=qwen2.5:3b
LLM_TIMEOUT_SECONDS=90
```

Restart the backend after changing these values. No model is downloaded automatically. `ollama list` shows valid model names. Keep the model server bound locally. This adapter accepts loopback HTTP endpoints only.

Normal setup: install `backend/requirements.txt`, run Uvicorn from backend, then `npm start` from frontend. In this workspace, the backend reuses the existing Python environment at `../../backend/.venv/Scripts/python.exe` when launched from this checkout's backend folder.

## 1. Personalized dish recommendation

This is an explainable content/history recommender, with an optional local-LLM reranking step. It is not a trained collaborative-filtering model.

1. Read only the signed-in customer's stored vegetarian preference, recorded allergies, favorite categories, and non-cancelled order history.
2. Exclude unavailable dishes, missing recipes, ingredients that cannot supply one portion, vegetarian mismatches, and recorded recipe-allergen conflicts.
3. Score remaining dishes: favorite-category bonus + bounded previous-purchase weight + bounded category-history weight + a smaller global popularity weight.
4. Show up to six dishes with evidence-derived explanations. New users receive popularity-based suggestions.
5. Optionally send at most twelve already-filtered candidates to Ollama for ranking. Names, categories and anonymous evidence are sent; no customer identity or allergy profile is needed by the model.
6. Validate distinct returned IDs against that shortlist. Unknown IDs, duplicate IDs, invalid JSON, busy/offline models or timeouts trigger an explicitly labeled history-based fallback.

Customers can save their dietary preferences on this page. Filters reflect recorded recipes only; they do not establish medical safety or cross-contact protection. Menu browsing and checkout behavior are unchanged by recommendation filtering.

## 2. Demand forecasting and ingredient planning

This module uses scikit-learn, not a language model; there is no forecast prompt.

- Target: non-cancelled order count per hour.
- Input: up to 120 days, excluding today and the first potentially incomplete day.
- At least 35 full historical calendar days are required.
- Missing hours are filled with zero (an explicit assumption).
- Features: cyclic hour and weekday, weekend flag, and demand 1, 2 and 3 weeks earlier.
- Candidate: `RandomForestRegressor`, 80 trees, depth 10, deterministic random seed 42.
- Validation: train on earlier observations; hold out the latest seven full days (168 hours), with no shuffled split or future lag values.
- Baseline: mean demand at the same hour over the previous three weeks.
- Compare hourly mean absolute error (MAE); select the better model. A baseline win is shown honestly.
- Refit on all available training data, predict a bridge for today, then publish the next 3, 7 or 14 full days.
- Show daily totals, expected peak hour, hourly bars, validation errors and training dates.

Ingredient consumption = predicted order count × historical ingredient quantity per order (last 28 days, using current recipes).

Suggested purchase = max(0, predicted consumption + reorder reserve − current stock). Piece units are rounded upward.

These are planning estimates, not guaranteed demand or a staffing schedule. No orders, ingredient stock or purchase orders are modified. Known stock shortages do not suppress demand forecasts: this forecasts observed ordering demand, not feasible production. Current recipes may differ from recipes used historically. Historical orders include demo data, so measured error is demonstration performance, not real-world validation.

## 3. Local review analysis

1. Staff choose a period and bounded recent sample (8, 24 or 48 reviews in the UI).
2. Full-period review count and average star rating are computed in SQL. Only non-empty text reviews in the period up to the current time are sampled.
3. Email addresses, phone-like numbers, links and known customer full names are redacted. This is best-effort redaction, not a general anonymization guarantee.
4. Obvious instruction-injection text is excluded and counted. Other text remains untrusted data inside a JSON user message.
5. Ollama classifies one review at a time into positive, neutral, negative or mixed sentiment and supported complaint topics. Individual requests and short examples reduce cross-review confusion with a small local model.
6. Pydantic validates JSON shape, sentiment and topic enums. Review IDs must match exactly and complaint evidence must occur in the supplied redacted review text (case-insensitive match). Cold-food quotes must also contain temperature evidence; a positive classification cannot simultaneously contain complaints. Contradictions are rejected, not silently relabeled.
7. Cache accepted classifications in `ai_review_analysis`, keyed by review ID, redacted-content hash, model name and prompt version.
8. Calculate sentiment counts and complaint frequencies in Python. A topic is counted once per review. Show evidence review IDs and quotes.
9. Send aggregate counts only to the model for a short manager briefing and up to three suggested actions. Action topics must exist in the analyzed sample.

Partial failures show warnings and pending counts; the interface does not silently replace LLM results with keyword guesses. Larger samples take longer on local hardware. The summary is generated text and still needs human review; the numerical counts and evidence are displayed separately. Cached classification avoids repeating the expensive reading step, while the summary is regenerated on each run.

## API

| Method | Path | Access |
|---|---|---|
| GET | `/api/ai/status` | Signed in |
| GET / PUT | `/api/ai/profile` | Customer |
| GET | `/api/ai/recommendations?use_llm=false` | Customer |
| GET | `/api/ai/forecast?days=7` | Staff |
| POST | `/api/ai/reviews?days=30&limit=8` | Staff |
| GET | `/api/ai/prompts` | Staff |

The existing backend session and role dependencies protect these routes; Angular guards are only navigation helpers. The AI layer has no tool-calling or shell execution and cannot purchase ingredients or change orders.

## Exact prompts

The authoritative strings used at runtime are in `backend/app/ai/prompts.py`. They are also visible in the dashboard under Prompts & methodology and exported in `AI_PROMPTS.md`.

Each request uses a system prompt and a separate JSON user message. Recommendation data contains candidate IDs, names, categories and ranking evidence. Classification data contains review IDs and redacted text. Summary data contains sample size, sentiment counts and complaint counts. The Ollama chat request uses a JSON schema, `stream: false`, temperature 0, bounded output and a timeout.

## Verification

```powershell
# From this checkout's backend:
..\..\backend\.venv\Scripts\python.exe -m unittest discover -p "test_*.py" -v
..\..\backend\.venv\Scripts\python.exe check_ai_local.py
# From frontend:
npm.cmd run build
```

The automated tests use temporary databases and stubbed inference. The separate smoke script signs into demo accounts, tests real local-model inference, then logs out; it writes accepted review classifications to the demo analysis cache. The existing operational database is backed up before the additive AI cache migration.

Reference documentation: [Ollama chat API](https://docs.ollama.com/api/chat), [scikit-learn lagged time-series features](https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html).
