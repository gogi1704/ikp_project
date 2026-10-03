import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ConsiliumUnavailable(RuntimeError):
    pass


def _create_link(path, payload):
    origin = os.environ.get('CONSILIUM_API_ORIGIN', '').strip().rstrip('/')
    secret = os.environ.get('CONSILIUM_INTEGRATION_SECRET', '').strip()
    if not origin or not secret:
        raise ConsiliumUnavailable('Интеграция с «Консилиумом» не настроена')
    body = json.dumps(payload, ensure_ascii=False).encode()
    request = Request(
        origin + path, data=body, method='POST',
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


def create_access_link(inn, company):
    return _create_link('/api/integrations/ikp/access', {
        'inn': str(inn or ''), 'company': str(company or ''),
    })


def create_masterclass_link(inn, company, masterclass_code):
    result = _create_link('/api/integrations/ikp/masterclass', {
        'inn': str(inn or ''), 'company': str(company or ''),
        'masterclass_code': str(masterclass_code or ''),
    })
    result['masterclassCode'] = str(masterclass_code or '')
    return result
