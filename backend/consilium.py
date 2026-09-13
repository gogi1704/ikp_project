import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ConsiliumUnavailable(RuntimeError):
    pass


def create_access_link(inn, company):
    origin = os.environ.get('CONSILIUM_API_ORIGIN', '').strip().rstrip('/')
    secret = os.environ.get('CONSILIUM_INTEGRATION_SECRET', '').strip()
    if not origin or not secret:
        raise ConsiliumUnavailable('Интеграция с «Консилиумом» не настроена')
    payload = json.dumps({'inn': str(inn or ''), 'company': str(company or '')}, ensure_ascii=False).encode()
    request = Request(
        origin + '/api/integrations/ikp/access', data=payload, method='POST',
        headers={
            'Authorization': 'Bearer ' + secret,
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json',
        },
    )
    try:
        with urlopen(request, timeout=float(os.environ.get('CONSILIUM_TIMEOUT_SECONDS', '5'))) as response:
            result = json.loads(response.read().decode())
    except HTTPError as error:
        try:
            detail = json.loads(error.read().decode()).get('detail')
        except (json.JSONDecodeError, UnicodeDecodeError):
            detail = None
        raise ConsiliumUnavailable(detail or '«Консилиум» отклонил создание ссылки') from error
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as error:
        raise ConsiliumUnavailable('Не удалось получить ссылку на «Консилиум»') from error
    url = str(result.get('url', ''))
    if not url.startswith(('https://', 'http://localhost:', 'http://127.0.0.1:')):
        raise ConsiliumUnavailable('«Консилиум» вернул некорректную ссылку')
    return {'url': url, 'trialDays': 5}
