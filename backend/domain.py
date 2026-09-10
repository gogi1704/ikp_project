import base64
import binascii
from decimal import Decimal, InvalidOperation

CORP = [('manager', 'Персональный менеджер', 0), ('delay', 'Отсрочка платежа', 0), ('monitor', 'Система мониторинга документооборота', 0), ('checkupPrice', 'Специальная цена на чек-апы во время медосмотра', 100)]
HEALTH = [('quiz', '«Умное» анкетирование', 0), ('aiAssist', 'ИИ-ассистент «Здоровый сотрудник»', 20), ('selfBuy', 'Индивидуальная покупка чек-апов', 0), ('liverKidney', 'Чек-ап «Здоровье печени и почек»', 2500), ('onco', 'Онко-ассистанс', 200)]
ADDONS = [('lmk', 'Новый бланк личной медицинской книжки', 650), ('sanmin', 'Санминимум', 700), ('staph', 'Исследование на стафилококк', 500), ('typhoid', 'Исследование на брюшной тиф', 200), ('intest', 'Исследование на кишечную инфекцию', 200)]

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
    profile = {k:string(data.get(k, ''), 150) for k in ('firstName','lastName','phone','messengerPhone')}
    profile['photo'] = image_data(data.get('photo', ''))
    return profile

def proposal(data, publish=False):
    p = {k: string(data.get(k, '')) for k in ['company', 'inn', 'lpr', 'mopFirstName', 'mopLastName', 'mopPhone', 'mopMessengerPhone']}
    if p['inn'] and (not p['inn'].isascii() or not p['inn'].isdigit() or len(p['inn']) not in (10, 12)):
        raise ValueError('ИНН должен содержать 10 или 12 цифр')
    p['count'] = integer(data.get('count', 1), 1)
    p['basePrice'] = money(data.get('basePrice', 2500)) / 100
    p['mopPhoto'] = image_data(data.get('mopPhoto', ''))
    for group, catalog in [('corp', CORP), ('health', HEALTH)]:
        p[group] = {}
        for code, _, price in catalog:
            item = data.get(group, {}).get(code, {})
            p[group][code] = {'on': boolean(item.get('on', True)), 'price': money(item.get('price', price)) / 100}
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
            on = boolean(item.get('on', offered if group != 'addons' else False))
            if on and not offered:
                raise ValueError('Услуга отсутствует в предложении')
            qty = integer(item.get('qty', 2 if code == 'liverKidney' else s['count']))
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
                rate = money(price if group == 'addons' else p[group][code]['price'])
                qty = item['qty'] if group == 'addons' else max(0, item['qty'] - 2) if code == 'liverKidney' else s['count']
                totals[group] += rate * qty
    totals['total'] = sum(totals.values())
    return totals
