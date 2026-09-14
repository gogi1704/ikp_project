import base64
import binascii
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import parse_qs, urlparse

CORP = [('manager', 'Персональный менеджер', 0), ('delay', 'Отсрочка платежа', 0), ('monitor', 'Контроль документов', 0), ('checkupPrice', 'Дополнительные чек-апы по корпоративной цене', 100)]
HEALTH = [('quiz', 'Онлайн-анкетирование перед медосмотром', 0), ('aiAssist', 'ИИ-ассистент «Здоровый сотрудник»', 20), ('selfBuy', 'Доступ к покупке доп. чек-апов', 0), ('liverKidney', 'Чек-ап «Здоровье печени и почек»', 2500), ('onco', 'Онко-ассистанс — сопровождение при онкологическом диагнозе', 200)]
ADDONS = [('lmk', 'Новый бланк личной медицинской книжки', 650), ('sanmin', 'Санминимум', 700), ('staph', 'Исследование на стафилококк', 500), ('typhoid', 'Исследование на брюшной тиф', 200), ('intest', 'Исследование на кишечную инфекцию', 200)]
DEFAULT_MANAGER_PHONE = '+7 (863) 322-67-66'
DEFAULT_MANAGER_MESSENGER_PHONE = '+7 (989) 506-74-60'

def integer(v, low=0, high=100000):
    if isinstance(v, bool) or not isinstance(v, int) or not low <= v <= high:
        raise ValueError(f'Ожидается целое число от {low} до {high}')
    return v

def money(v):
    try:
        d = Decimal(str(v))
        if not d.is_finite() or d < 0 or d > 10000000 or d != d.quantize(Decimal('.01')):
            raise ValueError('Цена должна быть от 0 до 10 000 000, не более двух знаков после запятой')
        return int(d * 100)
    except (InvalidOperation, TypeError):
        raise ValueError('Некорректная цена')

def whole_rubles(v):
    try:
        d = Decimal(str(v))
        if not d.is_finite() or d < 0 or d > 10000000:
            raise ValueError('Цена должна быть от 0 до 10 000 000 рублей')
        return int(d.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError):
        raise ValueError('Некорректная цена')

def string(v, limit=300):
    if not isinstance(v, str) or len(v) > limit:
        raise ValueError(f'Допустимо не более {limit} символов')
    return v.strip()

def boolean(v):
    if not isinstance(v, bool):
        raise ValueError('Некорректный выбор услуги')
    return v

def image_data(value):
    value = string(value, 400000)
    if not value:
        return ''
    if not value.startswith(('data:image/png;base64,', 'data:image/jpeg;base64,', 'data:image/webp;base64,')):
        raise ValueError('Фото: используйте PNG, JPEG или WebP')
    try:
        image = base64.b64decode(value.split(',', 1)[1], validate=True)
        if len(image) > 250000 or not (image.startswith(b'\x89PNG\r\n\x1a\n') or image.startswith(b'\xff\xd8\xff') or (image.startswith(b'RIFF') and image[8:12] == b'WEBP')):
            raise ValueError('Неверный формат или размер фото')
    except binascii.Error:
        raise ValueError('Неверный формат фото')
    return value

def manager_profile(data):
    profile = {k:string(data.get(k, ''), 150) for k in ('firstName','lastName')}
    profile['phone'] = string(data.get('phone', DEFAULT_MANAGER_PHONE), 150)
    profile['messengerPhone'] = string(data.get('messengerPhone', DEFAULT_MANAGER_MESSENGER_PHONE), 150)
    profile['photo'] = image_data(data.get('photo', ''))
    profile['messengers'] = messenger_accounts(data.get('messengers', []))
    return profile

def messenger_accounts(value):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 8:
        raise ValueError('Можно добавить не более 8 аккаунтов мессенджеров')
    result = []
    labels = {'telegram':'Telegram', 'whatsapp':'WhatsApp', 'max':'MAX', 'other':'Мессенджер'}
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError('Некорректные данные мессенджера')
        kind = string(raw.get('type', ''), 20).lower()
        account = string(raw.get('value', ''), 300)
        if kind not in labels or not account:
            raise ValueError('Выберите мессенджер и укажите аккаунт')
        if kind == 'telegram':
            candidate = account.removeprefix('@')
            if account.startswith(('http://', 'https://')):
                parsed = urlparse(account)
                if parsed.scheme != 'https' or parsed.hostname not in ('t.me', 'telegram.me') or not parsed.path.strip('/'):
                    raise ValueError('Telegram: укажите @имя или ссылку t.me')
                candidate = parsed.path.strip('/').split('/')[0]
            if not re.fullmatch(r'[A-Za-z0-9_]{5,32}', candidate):
                raise ValueError('Telegram: укажите корректное @имя или ссылку t.me')
            url, display = f'https://t.me/{candidate}', '@' + candidate
        elif kind == 'whatsapp':
            if account.startswith(('http://', 'https://')):
                parsed = urlparse(account)
                if parsed.scheme != 'https' or parsed.hostname not in ('wa.me', 'api.whatsapp.com'):
                    raise ValueError('WhatsApp: укажите номер или ссылку wa.me')
                candidate = parse_qs(parsed.query).get('phone', [''])[0] if parsed.hostname == 'api.whatsapp.com' else parsed.path
                digits = re.sub(r'\D', '', candidate)
            else:
                digits = re.sub(r'\D', '', account)
            if not 10 <= len(digits) <= 15:
                raise ValueError('WhatsApp: укажите полный номер в международном формате')
            url, display = f'https://wa.me/{digits}', account
        else:
            parsed = urlparse(account if '://' in account else 'https://' + account)
            allowed_hosts = ('max.ru', 'web.max.ru') if kind == 'max' else None
            if parsed.scheme != 'https' or not parsed.hostname or (allowed_hosts and parsed.hostname not in allowed_hosts):
                raise ValueError('MAX: вставьте ссылку профиля max.ru' if kind == 'max' else 'Укажите полную HTTPS-ссылку на аккаунт')
            url, display = parsed.geturl(), account
        result.append({'type':kind, 'label':labels[kind], 'value':display, 'url':url})
    return result

def proposal(data, publish=False):
    p = {k: string(data.get(k, '')) for k in ['company', 'inn', 'lpr', 'mopFirstName', 'mopLastName', 'mopPhone', 'mopMessengerPhone']}
    if p['inn'] and (not p['inn'].isascii() or not p['inn'].isdigit() or len(p['inn']) not in (10, 12)):
        raise ValueError('ИНН должен содержать 10 или 12 цифр')
    p['count'] = integer(data.get('count', 1), 1)
    p['basePrice'] = whole_rubles(data.get('basePrice', 2500))
    p['mopPhoto'] = image_data(data.get('mopPhoto', ''))
    p['mopMessengers'] = messenger_accounts(data.get('mopMessengers', []))
    recommended_count = 0
    for group, catalog in [('corp', CORP), ('health', HEALTH)]:
        p[group] = {}
        for code, _, price in catalog:
            item = data.get(group, {}).get(code, {})
            on = boolean(item.get('on', True))
            fixed = boolean(item.get('fixed', False))
            recommended = boolean(item.get('recommended', False))
            if (fixed or recommended) and not on:
                raise ValueError('Фиксировать и рекомендовать можно только включённую услугу')
            recommended_count += int(recommended)
            p[group][code] = {
                'on': on,
                'price': whole_rubles(item.get('price', price)),
                'fixed': fixed,
                'recommended': recommended,
            }
    p['addons'] = {}
    for code, _, price in ADDONS:
        item = data.get('addons', {}).get(code, {})
        qty = integer(item.get('qty', p['count']))
        if qty > p['count']:
            raise ValueError('Количество услуг не может превышать число сотрудников')
        p['addons'][code] = {'on': boolean(item.get('on', False)), 'qty': qty, 'price': whole_rubles(item.get('price', price))}
    if recommended_count > 1:
        raise ValueError('Рекомендованной можно отметить только одну услугу')
    if publish and (not p['company'] or not p['lpr']):
        raise ValueError('Укажите предприятие и ФИО руководителя')
    return p

def selection(p, data=None):
    data = data or {}
    s = {'count': integer(data.get('count', p['count']), 1)}
    for group, catalog in [('corp', CORP), ('health', HEALTH), ('addons', ADDONS)]:
        s[group] = {}
        for code, _, price in catalog:
            offered = group == 'addons' or p[group][code]['on']
            item = data.get(group, {}).get(code, {})
            preset = p.get('addons', {}).get(code, {}) if group == 'addons' else {}
            on = boolean(item.get('on', preset.get('on', False) if group == 'addons' else offered))
            if on and not offered:
                raise ValueError('Услуга отсутствует в предложении')
            if group != 'addons' and p[group][code].get('fixed', False) and not on:
                raise ValueError('Зафиксированную менеджером услугу нельзя отключить')
            qty = integer(item.get('qty', preset.get('qty', s['count']) if group == 'addons' else 2 if code == 'liverKidney' else s['count']))
            if group == 'addons' and qty > s['count']:
                raise ValueError('Количество услуг не может превышать число сотрудников')
            s[group][code] = {'on': on, 'qty': qty}
    for key in ['address', 'dates', 'comments']:
        s[key] = string(data.get(key, ''), 2000)
    return s

def calculate(p, s):
    totals = {'base': money(p['basePrice']) * s['count'], 'corp': 0, 'health': 0, 'addons': 0}
    for group, catalog in [('corp', CORP), ('health', HEALTH), ('addons', ADDONS)]:
        for code, _, price in catalog:
            item = s[group][code]
            if item['on']:
                rate = money(p.get('addons', {}).get(code, {}).get('price', price) if group == 'addons' else p[group][code]['price'])
                qty = item['qty'] if group == 'addons' else max(0, item['qty'] - 2) if code == 'liverKidney' else s['count']
                totals[group] += rate * qty
    totals['total'] = sum(totals.values())
    return totals
