"""Manual integration smoke check against the running local API and Ollama."""
import http.cookiejar
import json
from urllib.request import build_opener, HTTPCookieProcessor, Request


def client():
    return build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(opener, path, body=None, method=None):
    request = Request('http://127.0.0.1:8000' + path, data=json.dumps(body).encode() if body is not None else None,
                      headers={'Content-Type': 'application/json'}, method=method)
    with opener.open(request, timeout=300) as response:
        return None if response.status == 204 else json.load(response)


if __name__ == '__main__':
    staff = client()
    call(staff, '/api/auth/login', {'email': 'manager@nirvana.test', 'password': 'nirvana-demo'})
    print('Model:', json.dumps(call(staff, '/api/ai/status')), flush=True)
    forecast = call(staff, '/api/ai/forecast?days=3')
    print('Forecast:', json.dumps({k: forecast[k] for k in ('model', 'history_days', 'model_mae', 'baseline_mae', 'total_orders')}), flush=True)
    reviews = call(staff, '/api/ai/reviews?days=90&limit=4', {})
    print('Reviews:', json.dumps({k: reviews[k] for k in ('model', 'analyzed_count', 'flagged_count', 'pending_count', 'topics', 'insights', 'warnings')}), flush=True)
    call(staff, '/api/auth/logout', {})
    customer = client()
    call(customer, '/api/auth/login', {'email': 'demo@nirvana.test', 'password': 'nirvana-demo'})
    picks = call(customer, '/api/ai/recommendations?use_llm=true')
    print('Recommendations:', json.dumps({'mode': picks['mode'], 'names': [item['dish']['name'] for item in picks['items']], 'warning': picks['warning']}), flush=True)
    call(customer, '/api/auth/logout', {})
    assert reviews['analyzed_count'] > 0 and not reviews['warnings'], 'Real local review inference did not complete'
    assert picks['mode'] == 'local-llm-reranked', 'Real local recommendation inference did not complete'
