"""Server-side DaData organisation suggestions without exposing the API token."""
import json
import os
import threading
import time
from collections import defaultdict, deque
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_KEY = os.environ.get('DADATA_API_KEY', '').strip()
URL = os.environ.get('DADATA_SUGGESTIONS_URL', 'https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party').strip()
TIMEOUT = float(os.environ.get('DADATA_TIMEOUT_SECONDS', '5'))
CACHE_SECONDS = int(os.environ.get('DADATA_SUGGESTIONS_CACHE_SECONDS', '3600'))
_lock = threading.Lock()
_cache = {}
_requests = defaultdict(deque)

class Unavailable(RuntimeError): pass
class RateLimited(RuntimeError): pass

def suggest(query, client_key=''):
    digits = str(query).strip()
    if not digits.isdigit() or not 4 <= len(digits) <= 12:
        raise ValueError('Введите от 4 до 12 цифр ИНН')
    if not API_KEY:
        return []
    now = time.monotonic()
    with _lock:
        cached = _cache.get(digits)
        if cached and now - cached[0] < CACHE_SECONDS:
            return [dict(item) for item in cached[1]]
        bucket = _requests[str(client_key or 'unknown')[:100]]
        while bucket and now - bucket[0] >= 60: bucket.popleft()
        if len(bucket) >= 30: raise RateLimited('Слишком много запросов. Попробуйте немного позже')
        bucket.append(now)
    request = Request(URL, data=json.dumps({'query':digits,'count':7,'status':['ACTIVE']}).encode(), method='POST', headers={'Authorization':f'Token {API_KEY}','Content-Type':'application/json','Accept':'application/json'})
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read(256001)
        if len(raw) > 256000: raise Unavailable('Сервис подсказок вернул слишком большой ответ')
        payload = json.loads(raw.decode())
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise Unavailable('Подсказки организаций временно недоступны') from exc
    result, seen = [], set()
    for item in payload.get('suggestions', []):
        data = item.get('data') if isinstance(item, dict) and isinstance(item.get('data'), dict) else {}
        inn = str(data.get('inn', '')).strip()
        names = data.get('name') if isinstance(data.get('name'), dict) else {}
        name = str(item.get('value') or names.get('short_with_opf', '')).strip() if isinstance(item, dict) else ''
        if inn.startswith(digits) and inn not in seen and name:
            seen.add(inn); result.append({'inn':inn[:12], 'name':name[:300]})
        if len(result) == 7: break
    with _lock: _cache[digits] = (now, [dict(item) for item in result])
    return result
