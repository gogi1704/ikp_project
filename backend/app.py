import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from http.cookies import SimpleCookie
from urllib.parse import urlparse
from backend.domain import DEFAULT_MANAGER_MESSENGER_PHONE, DEFAULT_MANAGER_PHONE, proposal, selection, calculate, manager_profile

ROOT = Path(__file__).resolve().parent.parent

CYRILLIC_SLUG = str.maketrans({
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'e','ж':'zh','з':'z','и':'i','й':'y',
    'к':'k','л':'l','м':'m','н':'n','о':'o','п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f',
    'х':'h','ц':'ts','ч':'ch','ш':'sh','щ':'sch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
})

def public_link_slug(p):
    source = p.get('inn') or p.get('company', '')
    slug = re.sub(r'[^a-z0-9]+', '-', source.lower().translate(CYRILLIC_SLUG)).strip('-')[:48]
    return slug or 'proposal'

def load_dotenv(path):
    """Load a small .env file without replacing real process environment values."""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding='utf-8-sig').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        if '=' not in line:
            continue
        name, value = line.split('=', 1)
        name, value = name.strip(), value.strip()
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(name, value)

load_dotenv(ROOT / '.env')
from backend import company_suggestions, consilium

DB = os.environ.get('DATABASE_PATH', str(ROOT / 'data' / 'ikp.sqlite3'))
ORIGIN = os.environ.get('PUBLIC_ORIGIN', 'http://localhost:8000').rstrip('/')
SECURE = ORIGIN.startswith('https://')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '').strip()

@contextmanager
def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()

def init_db():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, login TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), csrf TEXT NOT NULL, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, owner TEXT NOT NULL REFERENCES users(id), body TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, created INTEGER NOT NULL, updated INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS links(id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES proposals(id), token TEXT UNIQUE NOT NULL, snapshot TEXT NOT NULL, expires INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL, viewed INTEGER);
        CREATE TABLE IF NOT EXISTS submissions(id TEXT PRIMARY KEY, link_id TEXT NOT NULL REFERENCES links(id), body TEXT NOT NULL, totals TEXT NOT NULL, created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, actor TEXT NOT NULL, event TEXT NOT NULL, entity TEXT NOT NULL, created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY, count INTEGER NOT NULL, reset INTEGER NOT NULL);
        ''')
        columns = {r['name'] for r in db.execute('PRAGMA table_info(users)')}
        if 'email' in columns and 'login' not in columns:
            db.execute('ALTER TABLE users RENAME COLUMN email TO login')
        for name, definition in [('role', "TEXT NOT NULL DEFAULT 'manager'"), ('active', 'INTEGER NOT NULL DEFAULT 1'), ('can_edit', 'INTEGER NOT NULL DEFAULT 1'), ('can_publish', 'INTEGER NOT NULL DEFAULT 1'), ('first_name', "TEXT NOT NULL DEFAULT ''"), ('last_name', "TEXT NOT NULL DEFAULT ''"), ('phone', "TEXT NOT NULL DEFAULT ''"), ('messenger_phone', "TEXT NOT NULL DEFAULT ''"), ('photo', "TEXT NOT NULL DEFAULT ''"), ('messengers', "TEXT NOT NULL DEFAULT '[]'")]:
            if name not in columns:
                db.execute(f'ALTER TABLE users ADD COLUMN {name} {definition}')
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version < 7:
            db.execute("UPDATE users SET phone=?, messenger_phone=? WHERE role='manager'", (DEFAULT_MANAGER_PHONE, DEFAULT_MANAGER_MESSENGER_PHONE))
        if version < 8:
            db.execute('CREATE TABLE submissions_v8(id TEXT PRIMARY KEY, link_id TEXT NOT NULL REFERENCES links(id), body TEXT NOT NULL, totals TEXT NOT NULL, created INTEGER NOT NULL)')
            db.execute('INSERT INTO submissions_v8 SELECT id,link_id,body,totals,created FROM submissions')
            db.execute('DROP TABLE submissions')
            db.execute('ALTER TABLE submissions_v8 RENAME TO submissions')
        db.execute('CREATE INDEX IF NOT EXISTS submissions_link_id_idx ON submissions(link_id)')
        db.execute('PRAGMA user_version=8')
        if not db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
            insert_user(db, 'admin', secrets.token_urlsafe(32), role='admin')

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

def validate_credentials(login, password):
    if not isinstance(login, str) or not re.fullmatch(r'[a-zA-Z0-9_.@+\-]{3,254}', login.strip()):
        raise ValueError('Логин: от 3 до 254 символов, латинские буквы, цифры и знаки _ . - @ +')
    if not isinstance(password, str) or not 6 <= len(password) <= 256:
        raise ValueError('Пароль должен содержать от 6 до 256 символов')
    return login.strip().lower()

def insert_user(db, login, password, role='manager', can_edit=True, can_publish=True, profile=None):
    login = validate_credentials(login, password)
    if role not in ('manager', 'admin'):
        raise ValueError('Некорректная роль')
    uid = secrets.token_hex(16)
    salt = secrets.token_hex(16)
    profile = manager_profile(profile or {})
    try:
        db.execute('INSERT INTO users(id,login,salt,password,role,can_edit,can_publish,first_name,last_name,phone,messenger_phone,photo,messengers) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (uid, login, salt, password_hash(password, salt), role, int(can_edit), int(can_publish), profile['firstName'], profile['lastName'], profile['phone'], profile['messengerPhone'], profile['photo'], json.dumps(profile['messengers'], ensure_ascii=False)))
    except sqlite3.IntegrityError:
        raise Error(409, 'Пользователь с таким логином уже существует')
    return uid

def create_user(login, password, role='manager'):
    with connect() as db:
        return insert_user(db, login, password, role)

def permissions(data):
    values = [data.get(k, True) for k in ('active', 'can_edit', 'can_publish')]
    if any(type(v) is not bool for v in values):
        raise ValueError('Права доступа должны быть логическими значениями')
    return values

def identity(row):
    return {'login':row['login'], 'csrf':row['csrf'], 'role':row['role'], 'can_edit':bool(row['can_edit']), 'can_publish':bool(row['can_publish']), 'profile':profile_from_row(row)}

def profile_from_row(row):
    try:
        messengers = json.loads(row['messengers'] or '[]')
        if not isinstance(messengers, list):
            messengers = []
    except (json.JSONDecodeError, TypeError):
        messengers = []
    return {'firstName':row['first_name'], 'lastName':row['last_name'], 'phone':row['phone'], 'messengerPhone':row['messenger_phone'], 'photo':row['photo'], 'messengers':messengers}

def apply_manager_profile(p, row):
    profile = profile_from_row(row)
    p['mopFirstName'] = profile['firstName']
    p['mopLastName'] = profile['lastName']
    p['mopPhone'] = profile['phone']
    p['mopMessengerPhone'] = profile['messengerPhone']
    p['mopPhoto'] = profile['photo']
    p['mopMessengers'] = profile['messengers']
    return p

def submission_from_row(row):
    item = dict(row)
    item['body'] = json.loads(item['body'])
    item['totals'] = json.loads(item['totals'])
    snapshot = item.pop('proposal_snapshot', None)
    if snapshot:
        item['proposal'] = json.loads(snapshot)
    return item

class Error(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message

def audit(db, actor, event, entity):
    db.execute('INSERT INTO audit(actor,event,entity,created) VALUES(?,?,?,?)', (actor, event, entity, int(time.time())))

DEFAULT_CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
CLIENT_PAGE_CSP = "default-src 'self'; script-src 'self' https://mc.yandex.ru https://yastatic.net; style-src 'self'; img-src 'self' data: https://mc.yandex.ru; connect-src 'self' https://mc.yandex.ru wss://mc.yandex.ru; frame-src https://mc.yandex.ru; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"

def application(env, start_response):
    status, headers = 200, []
    try:
        result, extra = route(env)
        headers += extra
        if isinstance(result, bytes):
            body = result
        else:
            body = json.dumps(result, ensure_ascii=False).encode()
            headers.append(('Content-Type', 'application/json; charset=utf-8'))
    except Error as e:
        status, body = e.status, json.dumps({'error': e.message}, ensure_ascii=False).encode()
        headers.append(('Content-Type', 'application/json; charset=utf-8'))
    except (ValueError, TypeError, AttributeError, KeyError) as e:
        status, body = 400, json.dumps({'error': str(e) if isinstance(e, ValueError) else 'Некорректные данные'}, ensure_ascii=False).encode()
        headers.append(('Content-Type', 'application/json; charset=utf-8'))
    except consilium.ConsiliumUnavailable as e:
        status, body = 503, json.dumps({'error': str(e)}, ensure_ascii=False).encode()
        headers.append(('Content-Type', 'application/json; charset=utf-8'))
    except Exception:
        import logging
        logging.exception('Request failed')
        status, body = 500, b'{"error":"Internal server error"}'
    csp = CLIENT_PAGE_CSP if env.get('PATH_INFO', '/').startswith('/p/') else DEFAULT_CSP
    headers += [('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'no-referrer'), ('X-Frame-Options', 'DENY'), ('Content-Security-Policy', csp), ('Content-Length', str(len(body)))]
    if SECURE:
        headers.append(('Strict-Transport-Security', 'max-age=31536000'))
    labels = {200:'OK',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',409:'Conflict',410:'Gone',413:'Payload Too Large',415:'Unsupported Media Type',429:'Too Many Requests',500:'Internal Server Error',503:'Service Unavailable'}
    start_response(f'{status} {labels[status]}', headers)
    return [body]

def route(env):
    method, path = env['REQUEST_METHOD'], env.get('PATH_INFO', '/')
    now = int(time.time())
    data = {}
    if method in ('POST', 'PUT', 'DELETE'):
        if env.get('HTTP_ORIGIN') != ORIGIN:
            raise Error(403, 'Источник запроса не разрешён')
        size = int(env.get('CONTENT_LENGTH') or 0)
        if size > 500000:
            raise Error(413, 'Файл или запрос слишком большой')
        if env.get('CONTENT_TYPE', '').split(';')[0] != 'application/json':
            raise Error(415, 'Требуется JSON')
        data = json.loads(env['wsgi.input'].read(size) or b'{}')
        if not isinstance(data, dict):
            raise ValueError('Ожидается объект')
    if method == 'GET' and path in ('/', '/manager', '/manager/', '/login'):
        return (ROOT / 'static' / 'manager.html').read_bytes(), [('Content-Type', 'text/html; charset=utf-8')]
    if method == 'GET' and path in ('/admin', '/admin/'):
        return (ROOT / 'static' / 'admin.html').read_bytes(), [('Content-Type', 'text/html; charset=utf-8')]
    if method == 'GET' and path.startswith('/p/'):
        return (ROOT / 'static' / 'client.html').read_bytes(), [('Content-Type', 'text/html; charset=utf-8')]
    if method == 'GET' and path in ['/static/app.css', '/static/shared.js', '/static/manager.js', '/static/client.js', '/static/admin.js', '/static/catalog.json', '/static/logo.png', '/static/corporate-care.mp4', '/static/materials/onco-assistance.pptx', '/static/materials/corporate-checkups-price.xlsx']:
        ext = Path(path).suffix
        return (ROOT / path.lstrip('/')).read_bytes(), [('Content-Type', {'.css':'text/css', '.js':'text/javascript', '.json':'application/json', '.png':'image/png', '.mp4':'video/mp4', '.pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation', '.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}[ext])]
    with connect() as db:
        if path == '/healthz' and method == 'GET':
            db.execute('SELECT 1')
            return {'status':'ok'}, []
        if path == '/api/login' and method == 'POST':
            key = digest(env.get('REMOTE_ADDR', 'unknown'))
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM attempts WHERE reset<?', (now,))
            a = db.execute('SELECT * FROM attempts WHERE key=?', (key,)).fetchone()
            if a and a['count'] >= 10:
                raise Error(429, 'Слишком много попыток. Повторите через 15 минут')
            db.execute('INSERT INTO attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1', (key, now + 900))
            db.commit()
            login = str(data.get('login', '')).lower().strip()
            password = str(data.get('password', ''))
            if not login:
                if not ADMIN_PASSWORD or not hmac.compare_digest(password, ADMIN_PASSWORD):
                    raise Error(401, 'Неверный пароль')
                u = db.execute("SELECT * FROM users WHERE role='admin' ORDER BY rowid LIMIT 1").fetchone()
                if not u or not u['active']:
                    raise Error(401, 'Неверный пароль')
            else:
                u = db.execute('SELECT * FROM users WHERE login=?', (login,)).fetchone()
                salt = u['salt'] if u else '00'*16
                candidate = password_hash(password, salt)
                if not u or not hmac.compare_digest(candidate, u['password']) or not u['active']:
                    raise Error(401, 'Неверный логин или пароль')
                # Serialize login with administrator changes and recheck credentials.
                db.execute('BEGIN IMMEDIATE')
                fresh = db.execute('SELECT * FROM users WHERE id=?', (u['id'],)).fetchone()
                if not fresh['active'] or fresh['password'] != u['password']:
                    raise Error(401, 'Неверный логин или пароль')
                u = fresh
            token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            db.execute('DELETE FROM sessions WHERE expires<?', (now,))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (digest(token),u['id'],csrf,now+28800))
            audit(db,u['id'],'login',u['id'])
            return identity(dict(u) | {'csrf':csrf}), [('Set-Cookie',f'ikp_session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'+('; Secure' if SECURE else ''))]
        if path.startswith('/api/public/'):
            parts = path.split('/')
            token = parts[3]
            link = db.execute('SELECT * FROM links WHERE token=?', (digest(token),)).fetchone()
            if not link:
                raise Error(404,'Предложение не найдено')
            if link['revoked']:
                raise Error(410,'Ссылка отозвана. Обратитесь к менеджеру')
            p = json.loads(link['snapshot'])
            existing = db.execute('SELECT * FROM submissions WHERE link_id=? ORDER BY created DESC,rowid DESC LIMIT 1', (link['id'],)).fetchone()
            if method == 'GET' and len(parts) == 4:
                db.execute('UPDATE links SET viewed=COALESCE(viewed,?) WHERE id=?',(now,link['id']))
                return {'proposal':p,'selection':json.loads(existing['body']) if existing else selection(p), 'receipt':None}, []
            if method == 'POST' and len(parts) == 5 and parts[4] in ('quote','submit'):
                s = selection(p,data)
                totals = calculate(p,s)
                if parts[4] == 'quote':
                    return totals, []
                access = consilium.create_access_link(p.get('inn'), p.get('company'))
                db.execute('BEGIN IMMEDIATE')
                fresh = db.execute('SELECT * FROM links WHERE id=?',(link['id'],)).fetchone()
                if fresh['revoked']:
                    raise Error(410,'Ссылка отозвана')
                receipt = secrets.token_hex(12)
                db.execute('INSERT INTO submissions VALUES(?,?,?,?,?)',(receipt,link['id'],json.dumps(s),json.dumps(totals),now))
                audit(db,'client','submitted',link['proposal_id'])
                return {'receipt':receipt,'totals':totals,'consilium':access}, []
            raise Error(404,'Страница не найдена')
        if path.startswith('/api/'):
            if method != 'GET':
                db.execute('BEGIN IMMEDIATE')
            cookie = SimpleCookie()
            cookie.load(env.get('HTTP_COOKIE',''))
            token = cookie.get('ikp_session')
            session = db.execute('SELECT s.*,u.login,u.role,u.can_edit,u.can_publish,u.first_name,u.last_name,u.phone,u.messenger_phone,u.photo,u.messengers FROM sessions s JOIN users u ON u.id=s.user_id WHERE token=? AND expires>? AND u.active=1', (digest(token.value) if token else '',now)).fetchone()
            if not session:
                raise Error(401,'Войдите в панель менеджера')
            uid = session['user_id']
            if method != 'GET' and not hmac.compare_digest(env.get('HTTP_X_CSRF_TOKEN',''),session['csrf']):
                raise Error(403,'Обновите страницу и повторите')
            if path == '/api/me' and method == 'GET':
                return identity(session), []
            if path == '/api/logout' and method == 'POST':
                db.execute('DELETE FROM sessions WHERE token=?',(session['token'],))
                return {}, [('Set-Cookie','ikp_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')]
            if path.startswith('/api/admin/'):
                if session['role'] != 'admin':
                    raise Error(403, 'Доступ только для администратора')
                if path == '/api/admin/managers' and method == 'GET':
                    managers = []
                    for row in db.execute("SELECT * FROM users WHERE role='manager' ORDER BY login"):
                        managers.append({'id':row['id'],'login':row['login'],'active':row['active'],'can_edit':row['can_edit'],'can_publish':row['can_publish']} | profile_from_row(row))
                    return managers, []
                if path == '/api/admin/managers' and method == 'POST':
                    active, can_edit, can_publish = permissions(data)
                    target = insert_user(db, data.get('login'), data.get('password'), can_edit=can_edit, can_publish=can_publish, profile=data.get('profile'))
                    db.execute('UPDATE users SET active=? WHERE id=?', (int(active), target))
                    audit(db, uid, 'manager_created', target)
                    return {'id':target}, []
                if path == '/api/admin/activity' and method == 'GET':
                    groups = []
                    link_count = submission_count = 0
                    rows = db.execute("SELECT p.id,p.owner,p.body,p.created,p.updated,u.login AS owner_login,u.first_name,u.last_name FROM proposals p JOIN users u ON u.id=p.owner ORDER BY p.updated DESC").fetchall()
                    for row in rows:
                        body = json.loads(row['body'])
                        links = [dict(item) for item in db.execute('SELECT id,revoked,created,viewed FROM links WHERE proposal_id=? ORDER BY created DESC', (row['id'],))]
                        submissions = [submission_from_row(item) for item in db.execute('SELECT s.*,l.snapshot AS proposal_snapshot FROM submissions s JOIN links l ON s.link_id=l.id WHERE l.proposal_id=? ORDER BY s.created DESC', (row['id'],))]
                        link_count += len(links)
                        submission_count += len(submissions)
                        owner_name = ' '.join(part for part in [row['first_name'], row['last_name']] if part)
                        groups.append({'id':row['id'],'owner':row['owner'],'ownerLogin':row['owner_login'],'ownerName':owner_name,'company':body.get('company',''),'inn':body.get('inn',''),'lpr':body.get('lpr',''),'created':row['created'],'updated':row['updated'],'links':links,'submissions':submissions})
                    return {'proposals':groups,'linkCount':link_count,'submissionCount':submission_count}, []
                parts = path.split('/')
                if len(parts) in (5, 6) and parts[3] == 'managers':
                    target = parts[4]
                    user = db.execute("SELECT * FROM users WHERE id=? AND role='manager'", (target,)).fetchone()
                    if not user:
                        raise Error(404, 'Менеджер не найден')
                    if method == 'PUT' and len(parts) == 5:
                        active, can_edit, can_publish = permissions(data)
                        db.execute('UPDATE users SET active=?,can_edit=?,can_publish=? WHERE id=?', (int(active),int(can_edit),int(can_publish),target))
                        db.execute('DELETE FROM sessions WHERE user_id=?', (target,))
                        audit(db, uid, f'manager_access:{int(active)}:{int(can_edit)}:{int(can_publish)}', target)
                        return {'id':target,'active':active,'can_edit':can_edit,'can_publish':can_publish}, []
                    if method == 'PUT' and len(parts) == 6 and parts[5] == 'profile':
                        profile = manager_profile(data.get('profile', {}))
                        db.execute('UPDATE users SET first_name=?,last_name=?,phone=?,messenger_phone=?,photo=?,messengers=? WHERE id=?', (profile['firstName'],profile['lastName'],profile['phone'],profile['messengerPhone'],profile['photo'],json.dumps(profile['messengers'], ensure_ascii=False),target))
                        audit(db, uid, 'manager_profile_updated', target)
                        return {'id':target,'profile':profile}, []
                    if method == 'DELETE' and len(parts) == 5:
                        proposal_ids = [row['id'] for row in db.execute('SELECT id FROM proposals WHERE owner=?', (target,))]
                        if proposal_ids:
                            placeholders = ','.join('?' for _ in proposal_ids)
                            link_ids = [row['id'] for row in db.execute(f'SELECT id FROM links WHERE proposal_id IN ({placeholders})', proposal_ids)]
                            if link_ids:
                                link_placeholders = ','.join('?' for _ in link_ids)
                                db.execute(f'DELETE FROM submissions WHERE link_id IN ({link_placeholders})', link_ids)
                            db.execute(f'DELETE FROM links WHERE proposal_id IN ({placeholders})', proposal_ids)
                            db.execute(f'DELETE FROM proposals WHERE id IN ({placeholders})', proposal_ids)
                        db.execute('DELETE FROM sessions WHERE user_id=?', (target,))
                        db.execute('DELETE FROM users WHERE id=?', (target,))
                        audit(db, uid, 'manager_deleted', target)
                        return {}, []
                    if method == 'POST' and len(parts) == 6 and parts[5] == 'password':
                        validate_credentials(user['login'], data.get('password'))
                        salt = secrets.token_hex(16)
                        db.execute('UPDATE users SET salt=?,password=? WHERE id=?', (salt,password_hash(data['password'],salt),target))
                        db.execute('DELETE FROM sessions WHERE user_id=?', (target,))
                        audit(db, uid, 'manager_password_reset', target)
                        return {}, []
                raise Error(404, 'Страница не найдена')
            if session['role'] != 'manager':
                raise Error(403, 'Используйте панель администратора')
            if path == '/api/company-suggestions' and method == 'POST':
                try:
                    return {'suggestions':company_suggestions.suggest(data.get('query', ''), env.get('REMOTE_ADDR', 'unknown'))}, []
                except company_suggestions.RateLimited as exc:
                    raise Error(429, str(exc))
                except company_suggestions.Unavailable as exc:
                    raise Error(503, str(exc))
            if path == '/api/activity' and method == 'GET':
                groups = []
                link_count = submission_count = 0
                for row in db.execute('SELECT id,body,created,updated FROM proposals WHERE owner=? ORDER BY updated DESC', (uid,)):
                    body = json.loads(row['body'])
                    links = [dict(item) for item in db.execute('SELECT id,revoked,created,viewed FROM links WHERE proposal_id=? ORDER BY created DESC', (row['id'],))]
                    submissions = [submission_from_row(item) for item in db.execute('SELECT s.*,l.snapshot AS proposal_snapshot FROM submissions s JOIN links l ON s.link_id=l.id WHERE l.proposal_id=? ORDER BY s.created DESC', (row['id'],))]
                    link_count += len(links)
                    submission_count += len(submissions)
                    groups.append({'id':row['id'],'company':body.get('company',''),'lpr':body.get('lpr',''),'created':row['created'],'updated':row['updated'],'links':links,'submissions':submissions})
                return {'proposals':groups,'linkCount':link_count,'submissionCount':submission_count}, []
            if path.startswith('/api/proposals') and method != 'GET':
                publishing = path.endswith(('/publish', '/revoke'))
                if not session['can_publish' if publishing else 'can_edit']:
                    raise Error(403, 'Нет права на публикацию и отзыв ссылок' if publishing else 'Нет права на создание и редактирование предложений')
            if path == '/api/proposals' and method == 'GET':
                rows = db.execute('SELECT * FROM proposals WHERE owner=? ORDER BY updated DESC',(uid,)).fetchall()
                return [dict(r) | {'body':apply_manager_profile(proposal(json.loads(r['body'])), session)} for r in rows], []
            if path == '/api/proposals' and method == 'POST':
                p, pid = apply_manager_profile(proposal(data), session), secrets.token_hex(16)
                db.execute('INSERT INTO proposals VALUES(?,?,?,1,?,?)',(pid,uid,json.dumps(p),now,now))
                audit(db,uid,'created',pid)
                return {'id':pid,'version':1,'body':p}, []
            parts = path.split('/')
            if len(parts) >= 4 and parts[2] == 'proposals':
                pid = parts[3]
                row = db.execute('SELECT * FROM proposals WHERE id=? AND owner=?',(pid,uid)).fetchone()
                if not row:
                    raise Error(404,'Предложение не найдено')
                if method == 'PUT' and len(parts) == 4:
                    p = apply_manager_profile(proposal(data['body']), session)
                    updated = db.execute('UPDATE proposals SET body=?,version=version+1,updated=? WHERE id=? AND version=?',(json.dumps(p),now,pid,data.get('version')))
                    if not updated.rowcount:
                        raise Error(409,'Предложение изменено в другой вкладке. Обновите страницу')
                    audit(db,uid,'updated',pid)
                    return {'id':pid,'version':row['version']+1,'body':p}, []
                if method == 'DELETE' and len(parts) == 4:
                    link_ids = [item['id'] for item in db.execute('SELECT id FROM links WHERE proposal_id=?', (pid,))]
                    if link_ids:
                        placeholders = ','.join('?' for _ in link_ids)
                        db.execute(f'DELETE FROM submissions WHERE link_id IN ({placeholders})', link_ids)
                    db.execute('DELETE FROM links WHERE proposal_id=?', (pid,))
                    db.execute('DELETE FROM proposals WHERE id=?', (pid,))
                    audit(db,uid,'deleted',pid)
                    return {}, []
                if method == 'GET' and len(parts) == 5 and parts[4] == 'activity':
                    links = [dict(r) for r in db.execute('SELECT id,revoked,created,viewed FROM links WHERE proposal_id=? ORDER BY created DESC',(pid,))]
                    subs = [submission_from_row(r) for r in db.execute('SELECT s.*,l.snapshot AS proposal_snapshot FROM submissions s JOIN links l ON s.link_id=l.id WHERE l.proposal_id=?',(pid,))]
                    return {'links':links,'submissions':subs}, []
                if method == 'POST' and len(parts) == 5 and parts[4] == 'publish':
                    p = apply_manager_profile(proposal(json.loads(row['body']),True), session)
                    token = public_link_slug(p) + '-' + secrets.token_urlsafe(32)
                    lid = secrets.token_hex(16)
                    db.execute('INSERT INTO links(id,proposal_id,token,snapshot,expires,created) VALUES(?,?,?,?,?,?)',(lid,pid,digest(token),json.dumps(p),0,now))
                    audit(db,uid,'published',pid)
                    return {'url':ORIGIN+'/p/'+token}, []
                if method == 'POST' and len(parts) == 5 and parts[4] == 'revoke':
                    updated = db.execute('UPDATE links SET revoked=1 WHERE proposal_id=? AND id=?',(pid,data.get('id')))
                    if not updated.rowcount:
                        raise Error(404,'Ссылка не найдена')
                    audit(db,uid,'revoked',pid)
                    return {}, []
        raise Error(404,'Страница не найдена')
