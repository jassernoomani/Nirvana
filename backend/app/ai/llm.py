"""Ollama adapter: loopback only, bounded JSON output, no tools or shell access."""
import json
import os
import threading
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pydantic import BaseModel, ValidationError

_lock = threading.Lock()


class LocalModelError(RuntimeError):
    pass


class ModelUnavailable(LocalModelError):
    """The model cannot be reached or is busy: retrying other reviews now would only wait for timeouts."""


def settings():
    return {'base_url': os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').rstrip('/'),
            'model': os.getenv('LLM_MODEL', 'qwen2.5:3b'),
            'timeout': min(180, max(5, int(os.getenv('LLM_TIMEOUT_SECONDS', '90'))))}


def request_json(path, body=None):
    config = settings()
    parsed = urlparse(config['base_url'])
    if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1') or parsed.username or parsed.password:
        raise ModelUnavailable('Configure OLLAMA_BASE_URL as a local HTTP Ollama endpoint.')
    req = Request(config['base_url'] + path, data=json.dumps(body).encode() if body is not None else None,
                  headers={'Content-Type': 'application/json'})
    try:
        with urlopen(req, timeout=config['timeout']) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise LocalModelError('The local model response exceeded the size limit.')
            return json.loads(raw)
    except (URLError, HTTPError, TimeoutError, OSError, ValueError) as exc:
        raise ModelUnavailable('Local model unavailable or response invalid. Check Ollama, LLM_MODEL and the configured timeout.') from exc


def status():
    config = settings()
    try:
        models = [item['name'] for item in request_json('/api/tags').get('models', [])]
        available = config['model'] in models or config['model'] + ':latest' in models
        return {'available': available, 'model': config['model'], 'installed_models': models,
                'message': 'Local model ready' if available else 'Configured model is not installed in Ollama'}
    except LocalModelError as exc:
        return {'available': False, 'model': config['model'], 'installed_models': [], 'message': str(exc)}


def generate(system: str, payload: dict, schema: type[BaseModel]):
    if not _lock.acquire(timeout=2):
        raise ModelUnavailable('Local model is busy. Try again after the current analysis finishes.')
    try:
        result = request_json('/api/chat', {'model': settings()['model'], 'stream': False,
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': json.dumps(payload)}],
            'format': schema.model_json_schema(), 'options': {'temperature': 0, 'num_predict': 1800, 'num_ctx': 8192}, 'keep_alive': '10m'})
        try:
            return schema.model_validate_json(result['message']['content'])
        except (KeyError, TypeError, ValidationError) as exc:
            raise LocalModelError('The local model returned output that failed schema validation. Try again.') from exc
    finally:
        _lock.release()
