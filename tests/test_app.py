import io
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from backend import app
from backend.domain import DEFAULT_MANAGER_MESSENGER_PHONE, DEFAULT_MANAGER_PHONE, proposal, selection, calculate

class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.consilium=patch('backend.app.consilium.create_access_link', return_value={'url':'https://consilium.example/ikp/test','trialDays':5})
        self.consilium.start()
        app.DB=str(Path(self.tmp.name)/'test.sqlite3')
        app.ADMIN_PASSWORD='admin-test-password'
        app.init_db()
        app.create_user('manager@example.test','long-test-password')
        self.cookie=''
        self.csrf=''
        self.call('/api/login','POST',{'login':'manager@example.test','password':'long-test-password'})

    def tearDown(self):
        self.consilium.stop()
        self.tmp.cleanup()

    def call(self,path,method='GET',body=None,authenticated=True,origin=None):
        raw=json.dumps(body or {}).encode()
        env={'REQUEST_METHOD':method,'PATH_INFO':path,'CONTENT_TYPE':'application/json','CONTENT_LENGTH':str(len(raw)),'wsgi.input':io.BytesIO(raw),'REMOTE_ADDR':'127.0.0.1','HTTP_ORIGIN':origin or app.ORIGIN,'HTTP_COOKIE':self.cookie if authenticated else '', 'HTTP_X_CSRF_TOKEN':self.csrf if authenticated else ''}
        response={}
        def start(status,headers):
            response['status']=int(status.split()[0])
            response['headers']=dict(headers)
        result=b''.join(app.application(env,start))
        if 'Set-Cookie' in response['headers']:
            self.cookie=response['headers']['Set-Cookie'].split(';')[0]
        data=json.loads(result)
        if 'csrf' in data:
            self.csrf=data['csrf']
        return response['status'],data

    def published(self):
        status,p=self.call('/api/proposals','POST',{'company':'ООО «Тест»','lpr':'Иван Иванов','count':10})
        self.assertEqual(status,200)
        status,l=self.call('/api/proposals/'+p['id']+'/publish','POST')
        self.assertEqual(status,200)
        return p,l['url'].split('/p/')[1]

    def test_full_flow_snapshot_and_multiple_submissions(self):
        p,token=self.published()
        endpoint='/api/public/'+token
        status,view=self.call(endpoint,authenticated=False)
        self.assertEqual(status,200)
        draft=p['body']|{'basePrice':9000}
        self.assertEqual(self.call('/api/proposals/'+p['id'],'PUT',{'body':draft,'version':1})[0],200)
        self.assertEqual(self.call(endpoint,authenticated=False)[1]['proposal']['basePrice'],2500)
        s=view['selection'];s['health']['liverKidney']['qty']=5
        s['addons']['sanmin']={'on':True,'qty':4}
        s['basePrice']=1;s['total']=1
        status,result=self.call(endpoint+'/submit','POST',s,False)
        self.assertEqual(status,200)
        self.assertEqual(result['consilium']['trialDays'],5)
        self.assertEqual(result['consilium']['url'],'https://consilium.example/ikp/test')
        self.assertEqual(result['totals']['total'],3850000)
        s['comments']='Повторная заявка'
        repeated=self.call(endpoint+'/submit','POST',s,False)[1]
        self.assertNotEqual(result['receipt'],repeated['receipt'])
        activity=self.call('/api/proposals/'+p['id']+'/activity')[1]['submissions']
        self.assertEqual(len(activity),2)
        self.assertEqual({item['id'] for item in activity},{result['receipt'],repeated['receipt']})
        repeated_item=next(item for item in activity if item['id']==repeated['receipt'])
        self.assertEqual(repeated_item['body']['comments'],'Повторная заявка')
        self.assertEqual(repeated_item['proposal']['basePrice'],2500)
        self.assertEqual(repeated_item['proposal']['company'],'ООО «Тест»')
        reopened=self.call(endpoint,authenticated=False)[1]
        self.assertIsNone(reopened['receipt'])
        self.assertEqual(reopened['selection']['comments'],'Повторная заявка')
        overview=self.call('/api/activity')[1]
        self.assertEqual((overview['linkCount'],overview['submissionCount']),(1,2))
        self.assertEqual(overview['proposals'][0]['id'],p['id'])
        self.assertEqual({item['id'] for item in overview['proposals'][0]['submissions']},{result['receipt'],repeated['receipt']})
        self.assertEqual(overview['proposals'][0]['submissions'][0]['proposal']['basePrice'],2500)

    def test_access_controls(self):
        p,token=self.published()
        self.assertEqual(self.call('/api/proposals',authenticated=False)[0],401)
        self.assertEqual(self.call('/api/proposals','POST',{},origin='https://evil.test')[0],403)
        self.assertEqual(self.call('/api/public/'+p['id'],authenticated=False)[0],404)
        self.csrf='wrong'
        self.assertEqual(self.call('/api/proposals','POST',{})[0],403)
        app.create_user('other@example.test','long-test-password')
        self.call('/api/login','POST',{'login':'other@example.test','password':'long-test-password'})
        self.assertEqual(self.call('/api/proposals/'+p['id']+'/activity')[0],404)
        self.assertEqual(self.call('/api/proposals')[1],[])
        self.assertEqual(self.call('/api/activity')[1]['linkCount'],0)

    def test_submission_is_not_saved_without_consilium_link(self):
        p,token=self.published()
        endpoint='/api/public/'+token
        selection=self.call(endpoint,authenticated=False)[1]['selection']
        with patch('backend.app.consilium.create_access_link', side_effect=app.consilium.ConsiliumUnavailable('Консилиум временно недоступен')):
            status,result=self.call(endpoint+'/submit','POST',selection,False)
        self.assertEqual(status,503)
        self.assertEqual(result['error'],'Консилиум временно недоступен')
        self.assertEqual(self.call('/api/proposals/'+p['id']+'/activity')[1]['submissions'],[])

    def test_client_video_is_served_as_mp4(self):
        env={'REQUEST_METHOD':'GET','PATH_INFO':'/static/corporate-care.mp4','wsgi.input':io.BytesIO(b''),'REMOTE_ADDR':'127.0.0.1'}
        response={}
        def start(status,headers):
            response['status']=int(status.split()[0]);response['headers']=dict(headers)
        body=b''.join(app.application(env,start))
        self.assertEqual(response['status'],200)
        self.assertEqual(response['headers']['Content-Type'],'video/mp4')
        self.assertTrue(body.startswith(b'\x00\x00\x00'))

    def test_client_materials_are_downloadable(self):
        materials={
            '/static/materials/onco-assistance.pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '/static/materials/corporate-checkups-price.xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }
        for path,content_type in materials.items():
            with self.subTest(path=path):
                env={'REQUEST_METHOD':'GET','PATH_INFO':path,'wsgi.input':io.BytesIO(b''),'REMOTE_ADDR':'127.0.0.1'}
                response={}
                def start(status,headers):
                    response['status']=int(status.split()[0]);response['headers']=dict(headers)
                body=b''.join(app.application(env,start))
                self.assertEqual(response['status'],200)
                self.assertEqual(response['headers']['Content-Type'],content_type)
                self.assertTrue(body.startswith(b'PK'))

    def test_manager_addon_presets_become_client_defaults(self):
        status,p=self.call('/api/proposals','POST',{
            'company':'ООО «Настройка»',
            'lpr':'Иванова Ивана Ивановича',
            'count':12,
            'addons':{'sanmin':{'on':True,'qty':7,'price':900}},
        })
        self.assertEqual(status,200)
        self.assertTrue(p['body']['addons']['sanmin']['on'])
        self.assertEqual(p['body']['addons']['sanmin']['qty'],7)
        self.assertEqual(p['body']['addons']['sanmin']['price'],900)
        self.assertEqual(p['body']['addons']['lmk']['price'],650)
        self.assertTrue(p['body']['addons']['lmk']['on'])
        self.assertEqual(p['body']['addons']['lmk']['qty'],0)
        token=self.call('/api/proposals/'+p['id']+'/publish','POST')[1]['url'].split('/p/')[1]
        public=self.call('/api/public/'+token,authenticated=False)[1]
        self.assertTrue(public['selection']['addons']['sanmin']['on'])
        self.assertEqual(public['selection']['addons']['sanmin']['qty'],7)
        self.assertEqual(public['proposal']['addons']['sanmin']['price'],900)
        self.assertEqual(self.call('/api/public/'+token+'/quote','POST',public['selection'],False)[1]['addons'],630000)
        self.assertTrue(public['selection']['addons']['lmk']['on'])
        self.assertEqual(public['selection']['addons']['lmk']['qty'],0)

        legacy=p['body'].copy()
        legacy.pop('addons')
        defaults=selection(legacy)
        self.assertTrue(defaults['addons']['sanmin']['on'])
        self.assertEqual(defaults['addons']['sanmin']['qty'],0)

    def test_links_ignore_expiry_but_respect_revocation(self):
        p,token=self.published()
        self.assertEqual(self.call('/api/proposals/'+p['id'],'PUT',{'body':p['body'],'version':0})[0],409)
        with app.connect() as db: db.execute('UPDATE links SET expires=0')
        self.assertEqual(self.call('/api/public/'+token,authenticated=False)[0],200)
        lid=self.call('/api/proposals/'+p['id']+'/activity')[1]['links'][0]['id']
        self.assertEqual(self.call('/api/proposals/'+p['id']+'/revoke','POST',{'id':lid})[0],200)
        self.assertEqual(self.call('/api/public/'+token,authenticated=False)[0],410)

    def test_activity_exposes_reopenable_link_url(self):
        p,token=self.published()
        link=self.call('/api/proposals/'+p['id']+'/activity')[1]['links'][0]
        self.assertEqual(link['url'],app.ORIGIN+'/p/'+token)
        with app.connect() as db: db.execute('UPDATE links SET plain_token=NULL WHERE id=?',(link['id'],))
        link=self.call('/api/proposals/'+p['id']+'/activity')[1]['links'][0]
        self.assertIsNone(link['url'])

    def test_public_link_contains_inn_or_company_slug_and_keeps_secret(self):
        status, with_inn = self.call('/api/proposals','POST',{'company':'ООО «Ромашка»','inn':'7707083893','lpr':'Иван Иванов'})
        self.assertEqual(status,200)
        inn_url = self.call('/api/proposals/'+with_inn['id']+'/publish','POST')[1]['url']
        inn_token = inn_url.split('/p/')[1]
        self.assertTrue(inn_token.startswith('7707083893-'))
        self.assertGreaterEqual(len(inn_token.removeprefix('7707083893-')),40)
        self.assertEqual(self.call('/api/public/'+inn_token,authenticated=False)[0],200)

        status, without_inn = self.call('/api/proposals','POST',{'company':'ООО «Ромашка»','lpr':'Пётр Петров'})
        self.assertEqual(status,200)
        company_url = self.call('/api/proposals/'+without_inn['id']+'/publish','POST')[1]['url']
        company_token = company_url.split('/p/')[1]
        self.assertTrue(company_token.startswith('ooo-romashka-'))
        self.assertEqual(self.call('/api/public/'+company_token,authenticated=False)[0],200)

    def test_validation_and_price_integrity(self):
        for value in [-1,1.5,True,100001]:
            self.assertEqual(self.call('/api/proposals','POST',{'count':value})[0],400)
        p=proposal({'count':10,'corp':{'delay':{'on':False,'price':0}}})
        s=selection(p)
        s['corp']['delay']['on']=True
        with self.assertRaises(ValueError):selection(p,s)
        s=selection(p);s['addons']['lmk']['qty']=11
        with self.assertRaises(ValueError):selection(p,s)
        p=proposal({'count':1,'basePrice':0.51})
        s=selection(p)
        self.assertEqual(p['basePrice'],1)
        self.assertTrue(all(isinstance(item['price'],int) for group in ('corp','health') for item in p[group].values()))
        self.assertEqual(calculate(p,s)['base'],100)
        self.assertEqual(calculate(p,s)['health'],22000)

    def test_fixed_service_cannot_be_disabled_but_recommended_can(self):
        status, row = self.call('/api/proposals','POST',{'company':'ООО «Тест»','lpr':'Иван Иванов','count':10})
        self.assertEqual(status,200)
        body = row['body']
        body['corp']['manager']['fixed'] = True
        body['health']['aiAssist']['recommended'] = True
        status, saved = self.call('/api/proposals/'+row['id'],'PUT',{'body':body,'version':row['version']})
        self.assertEqual(status,200)
        self.assertTrue(saved['body']['corp']['manager']['fixed'])
        self.assertTrue(saved['body']['health']['aiAssist']['recommended'])
        status, link = self.call('/api/proposals/'+row['id']+'/publish','POST')
        self.assertEqual(status,200)
        endpoint = '/api/public/'+link['url'].split('/p/')[1]
        view = self.call(endpoint,authenticated=False)[1]

        fixed_disabled = view['selection']
        fixed_disabled['corp']['manager']['on'] = False
        status, result = self.call(endpoint+'/quote','POST',fixed_disabled,False)
        self.assertEqual(status,400)
        self.assertIn('нельзя отключить',result['error'])

        recommended_disabled = self.call(endpoint,authenticated=False)[1]['selection']
        recommended_disabled['health']['aiAssist']['on'] = False
        self.assertEqual(self.call(endpoint+'/quote','POST',recommended_disabled,False)[0],200)

    def test_only_one_enabled_service_can_be_recommended_or_fixed(self):
        data = {'corp':{'manager':{'recommended':True},'delay':{'recommended':True}}}
        with self.assertRaisesRegex(ValueError,'только одну услугу'):
            proposal(data)
        with self.assertRaisesRegex(ValueError,'только включённую услугу'):
            proposal({'corp':{'manager':{'on':False,'fixed':True}}})
        with self.assertRaisesRegex(ValueError,'только включённую услугу'):
            proposal({'health':{'quiz':{'on':False,'recommended':True}}})

    def test_login_rate_limit(self):
        for _ in range(9):self.call('/api/login','POST',{'login':'bad','password':'bad'})
        self.assertEqual(self.call('/api/login','POST',{'login':'bad','password':'bad'})[0],429)

    def test_company_suggestions_are_private_and_return_safe_fields(self):
        self.assertEqual(self.call('/api/company-suggestions','POST',{'query':'7707'},authenticated=False)[0],401)
        with patch('backend.app.company_suggestions.suggest', return_value=[{'inn':'7707083893','name':'ПАО «Тест»'}]) as suggest:
            status, result = self.call('/api/company-suggestions','POST',{'query':'7707'})
            self.assertEqual(status,200)
            self.assertEqual(result,{'suggestions':[{'inn':'7707083893','name':'ПАО «Тест»'}]})
            suggest.assert_called_once_with('7707','127.0.0.1')
        self.assertEqual(self.call('/api/company-suggestions','POST',{'query':'77'})[0],400)

    def test_dotenv_loader_preserves_process_environment(self):
        import os
        env_file = Path(self.tmp.name) / '.env'
        env_file.write_text('IKP_TEST_VALUE=from-file\nIKP_EXISTING=file-value\n', encoding='utf-8')
        os.environ['IKP_EXISTING'] = 'process-value'
        try:
            app.load_dotenv(env_file)
            self.assertEqual(os.environ['IKP_TEST_VALUE'],'from-file')
            self.assertEqual(os.environ['IKP_EXISTING'],'process-value')
        finally:
            os.environ.pop('IKP_TEST_VALUE',None)
            os.environ.pop('IKP_EXISTING',None)

    def admin_login(self):
        self.assertEqual(self.call('/api/login','POST',{'password':app.ADMIN_PASSWORD})[0],200)

    def test_admin_boundary_and_creation(self):
        self.assertEqual(self.call('/api/admin/managers')[0],403)
        self.assertEqual(self.call('/api/admin/managers',authenticated=False)[0],401)
        self.admin_login()
        self.assertEqual(self.call('/api/proposals')[0],403)
        data={'login':'New_manager','password':'new-manager-password','can_edit':False,'can_publish':False}
        self.assertEqual(self.call('/api/admin/managers','POST',data)[0],200)
        self.assertEqual(self.call('/api/admin/managers','POST',data)[0],409)
        self.assertEqual(self.call('/api/admin/managers','POST',data|{'login':'bad name'})[0],400)
        self.assertEqual(self.call('/api/admin/managers','POST',data|{'can_edit':'false'})[0],400)
        users=self.call('/api/admin/managers')[1]
        self.assertEqual(len(users),2)
        self.assertFalse(any('password' in u or 'salt' in u for u in users))
        self.call('/api/login','POST',{'login':'new_manager','password':'new-manager-password'})
        self.assertEqual(self.call('/api/proposals')[0],200)
        self.assertEqual(self.call('/api/proposals','POST',{})[0],403)
        self.assertEqual(self.call('/api/admin/managers')[0],403)

    def test_admin_activity_lists_all_managers_data(self):
        p1,token1=self.published()
        view1=self.call('/api/public/'+token1,authenticated=False)[1]
        self.call('/api/public/'+token1+'/submit','POST',view1['selection'],False)
        self.admin_login()
        data={'login':'second_manager','password':'second-manager-password','can_edit':True,'can_publish':True}
        self.assertEqual(self.call('/api/admin/managers','POST',data)[0],200)
        self.call('/api/login','POST',{'login':'second_manager','password':'second-manager-password'})
        p2,token2=self.published()
        self.admin_login()
        self.assertEqual(self.call('/api/proposals')[0],403)
        status,overview=self.call('/api/admin/activity')
        self.assertEqual(status,200)
        self.assertEqual(overview['linkCount'],2)
        self.assertEqual(overview['submissionCount'],1)
        owners={g['id']:g['ownerLogin'] for g in overview['proposals']}
        self.assertEqual(owners[p1['id']],'manager@example.test')
        self.assertEqual(owners[p2['id']],'second_manager')
        with_submission=next(g for g in overview['proposals'] if g['id']==p1['id'])
        self.assertEqual(len(with_submission['submissions']),1)
        self.assertEqual(len(with_submission['links']),1)
        self.call('/api/login','POST',{'login':'manager@example.test','password':'long-test-password'})
        self.assertEqual(self.call('/api/admin/activity')[0],403)
        self.assertEqual(self.call('/api/admin/activity',authenticated=False)[0],401)

    def test_admin_login_by_password_only(self):
        app.ADMIN_PASSWORD=''
        self.assertEqual(self.call('/api/login','POST',{'password':'admin-test-password'})[0],401)
        app.ADMIN_PASSWORD='admin-test-password'
        status,body=self.call('/api/login','POST',{'password':'admin-test-password'})
        self.assertEqual(status,200)
        self.assertEqual(body['role'],'admin')
        status,body=self.call('/api/login','POST',{'password':'wrong-password'})
        self.assertEqual(status,401)
        self.assertEqual(body['error'],'Неверный пароль')
        self.assertEqual(self.call('/api/login','POST',{'password':'long-test-password'})[0],401)
        self.assertEqual(self.call('/api/login','POST',{'login':'manager@example.test','password':'long-test-password'})[0],200)

    def test_disable_and_password_reset_revoke_sessions(self):
        manager_cookie,manager_csrf=self.cookie,self.csrf
        self.admin_login()
        admin_cookie,admin_csrf=self.cookie,self.csrf
        user=self.call('/api/admin/managers')[1][0]
        target='/api/admin/managers/'+user['id']
        self.assertEqual(self.call(target,'PUT',{'active':False,'can_edit':True,'can_publish':True})[0],200)
        self.cookie,self.csrf=manager_cookie,manager_csrf
        self.assertEqual(self.call('/api/me')[0],401)
        self.assertEqual(self.call('/api/login','POST',{'login':user['login'],'password':'long-test-password'})[0],401)
        self.cookie,self.csrf=admin_cookie,admin_csrf
        self.call(target,'PUT',{'active':True,'can_edit':True,'can_publish':True})
        self.call('/api/login','POST',{'login':user['login'],'password':'long-test-password'})
        manager_cookie,manager_csrf=self.cookie,self.csrf
        self.cookie,self.csrf=admin_cookie,admin_csrf
        self.assertEqual(self.call(target+'/password','POST',{'password':'replacement-password'})[0],200)
        self.cookie,self.csrf=manager_cookie,manager_csrf
        self.assertEqual(self.call('/api/me')[0],401)
        self.assertEqual(self.call('/api/login','POST',{'login':user['login'],'password':'long-test-password'})[0],401)
        self.assertEqual(self.call('/api/login','POST',{'login':user['login'],'password':'replacement-password'})[0],200)

    def test_granular_permissions_preserve_proposals(self):
        p,token=self.published()
        self.admin_login()
        admin_cookie,admin_csrf=self.cookie,self.csrf
        user=self.call('/api/admin/managers')[1][0]
        target='/api/admin/managers/'+user['id']
        self.call(target,'PUT',{'active':True,'can_edit':False,'can_publish':True})
        self.call('/api/login','POST',{'login':user['login'],'password':'long-test-password'})
        self.assertEqual(self.call('/api/proposals/'+p['id'],'PUT',{'body':p['body'],'version':1})[0],403)
        self.assertEqual(self.call('/api/proposals/'+p['id']+'/publish','POST')[0],200)
        self.cookie,self.csrf=admin_cookie,admin_csrf
        self.call(target,'PUT',{'active':True,'can_edit':True,'can_publish':False})
        self.call('/api/login','POST',{'login':user['login'],'password':'long-test-password'})
        self.assertEqual(self.call('/api/proposals/'+p['id']+'/publish','POST')[0],403)
        self.assertEqual(self.call('/api/proposals/'+p['id']+'/revoke','POST',{})[0],403)
        self.assertEqual(self.call('/api/proposals/'+p['id'],'PUT',{'body':p['body'],'version':1})[0],200)
        self.assertEqual(self.call('/api/public/'+token,authenticated=False)[0],200)

    def test_schema_migration_preserves_accounts(self):
        import sqlite3
        legacy=str(Path(self.tmp.name)/'legacy.sqlite3')
        db=sqlite3.connect(legacy)
        db.execute('CREATE TABLE users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,salt TEXT NOT NULL,password TEXT NOT NULL)')
        db.execute("INSERT INTO users VALUES('legacy','old@example.test','salt','hash')")
        db.commit();db.close()
        app.DB=legacy
        app.init_db();app.init_db()
        with app.connect() as db:
            u=db.execute('SELECT * FROM users').fetchone()
            self.assertEqual(u['password'],'hash')
            self.assertEqual(u['login'],'old@example.test')
            self.assertEqual((u['role'],u['active'],u['can_edit'],u['can_publish']),('manager',1,1,1))
            self.assertEqual(u['phone'],DEFAULT_MANAGER_PHONE)
            self.assertEqual(u['messenger_phone'],DEFAULT_MANAGER_MESSENGER_PHONE)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],8)

    def test_submission_migration_preserves_existing_and_allows_repeat(self):
        proposal_row,_=self.published()
        link_id=self.call('/api/proposals/'+proposal_row['id']+'/activity')[1]['links'][0]['id']
        with app.connect() as db:
            db.execute('DROP TABLE submissions')
            db.execute('CREATE TABLE submissions(id TEXT PRIMARY KEY,link_id TEXT UNIQUE NOT NULL REFERENCES links(id),body TEXT NOT NULL,totals TEXT NOT NULL,created INTEGER NOT NULL)')
            db.execute('INSERT INTO submissions VALUES(?,?,?,?,?)',('old-submission',link_id,'{}','{}',1))
            db.execute('PRAGMA user_version=7')
        app.init_db()
        with app.connect() as db:
            db.execute('INSERT INTO submissions VALUES(?,?,?,?,?)',('new-submission',link_id,'{}','{}',2))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM submissions WHERE link_id=?',(link_id,)).fetchone()[0],2)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],8)

    def test_manager_profile_is_copied_to_new_proposals(self):
        self.admin_login()
        profile={'firstName':'Лариса','lastName':'Захарченко','phone':'+7 863 322-67-66','messengerPhone':'+7 989 506-74-60','photo':'','messengers':[]}
        status, created=self.call('/api/admin/managers','POST',{'login':'profile_manager','password':'profile-password','profile':profile})
        self.assertEqual(status,200)
        managers=self.call('/api/admin/managers')[1]
        saved=next(user for user in managers if user['id']==created['id'])
        self.assertEqual(saved['firstName'],'Лариса')
        self.call('/api/login','POST',{'login':'profile_manager','password':'profile-password'})
        me=self.call('/api/me')[1]
        self.assertEqual(me['profile'],profile)
        proposal_body=self.call('/api/proposals','POST',{})[1]['body']
        self.assertEqual(proposal_body['mopFirstName'],'Лариса')
        self.assertEqual(proposal_body['mopLastName'],'Захарченко')
        self.assertEqual(proposal_body['mopPhone'],'+7 863 322-67-66')
        self.assertEqual(proposal_body['mopMessengerPhone'],'+7 989 506-74-60')

    def test_new_manager_uses_mvp_phone_defaults(self):
        me=self.call('/api/me')[1]
        self.assertEqual(me['profile']['phone'],DEFAULT_MANAGER_PHONE)
        self.assertEqual(me['profile']['messengerPhone'],DEFAULT_MANAGER_MESSENGER_PHONE)
        proposal_body=self.call('/api/proposals','POST',{})[1]['body']
        self.assertEqual(proposal_body['mopPhone'],DEFAULT_MANAGER_PHONE)
        self.assertEqual(proposal_body['mopMessengerPhone'],DEFAULT_MANAGER_MESSENGER_PHONE)

    def test_manager_cannot_edit_profile_or_override_account_data_in_proposal(self):
        self.assertEqual(self.call('/api/profile','PUT',{'profile':{}})[0],404)
        self.admin_login()
        user=next(item for item in self.call('/api/admin/managers')[1] if item['login']=='manager@example.test')
        requested={
            'firstName':'Мария','lastName':'Орлова','phone':'+7 900 100-20-30','messengerPhone':'', 'photo':'',
            'messengers':[
                {'type':'telegram','value':'@maria_manager'},
                {'type':'whatsapp','value':'+7 (900) 100-20-30'},
                {'type':'max','value':'https://max.ru/maria_manager'},
            ],
        }
        status,result=self.call('/api/admin/managers/'+user['id']+'/profile','PUT',{'profile':requested})
        self.assertEqual(status,200)
        saved=result['profile']
        self.assertEqual(saved['messengers'][0]['url'],'https://t.me/maria_manager')
        self.assertEqual(saved['messengers'][1]['url'],'https://wa.me/79001002030')
        self.assertEqual(saved['messengers'][2]['url'],'https://max.ru/maria_manager')
        self.call('/api/login','POST',{'login':'manager@example.test','password':'long-test-password'})
        self.assertEqual(self.call('/api/me')[1]['profile'],saved)
        proposal_row=self.call('/api/proposals','POST',{'company':'ООО «Контакт»','lpr':'Иван Иванов'})[1]
        self.assertEqual(proposal_row['body']['mopMessengers'],saved['messengers'])
        tampered=proposal_row['body']|{'mopFirstName':'Подмена','mopPhone':'000','mopMessengers':[]}
        updated=self.call('/api/proposals/'+proposal_row['id'],'PUT',{'body':tampered,'version':proposal_row['version']})[1]
        self.assertEqual(updated['body']['mopFirstName'],saved['firstName'])
        self.assertEqual(updated['body']['mopPhone'],saved['phone'])
        self.assertEqual(updated['body']['mopMessengers'],saved['messengers'])
        link=self.call('/api/proposals/'+proposal_row['id']+'/publish','POST')[1]
        public=self.call('/api/public/'+link['url'].split('/p/')[1],authenticated=False)[1]
        self.assertEqual(public['proposal']['mopFirstName'],saved['firstName'])
        self.assertEqual(public['proposal']['mopPhone'],saved['phone'])
        self.assertEqual(public['proposal']['mopMessengers'],saved['messengers'])

    def test_messenger_links_reject_unsafe_or_wrong_hosts(self):
        self.admin_login()
        user=next(item for item in self.call('/api/admin/managers')[1] if item['login']=='manager@example.test')
        path='/api/admin/managers/'+user['id']+'/profile'
        base={'firstName':'','lastName':'','phone':'','messengerPhone':'','photo':''}
        invalid=[
            {'type':'telegram','value':'https://evil.test/user'},
            {'type':'whatsapp','value':'javascript:alert(1)'},
            {'type':'max','value':'https://evil.test/profile'},
            {'type':'other','value':'http://example.test/profile'},
        ]
        for messenger in invalid:
            self.assertEqual(self.call(path,'PUT',{'profile':base|{'messengers':[messenger]}})[0],400)

    def test_admin_updates_and_preserves_manager_profile(self):
        self.admin_login()
        managers=self.call('/api/admin/managers')[1]
        user=next(item for item in managers if item['login']=='manager@example.test')
        profile={'firstName':'Иван','lastName':'Иванов','phone':'+7 900 111-22-33','messengerPhone':'@ivanov','photo':'','messengers':[]}
        path='/api/admin/managers/'+user['id']
        status,result=self.call(path+'/profile','PUT',{'profile':profile})
        self.assertEqual(status,200)
        self.assertEqual(result['profile'],profile)
        saved=next(item for item in self.call('/api/admin/managers')[1] if item['id']==user['id'])
        self.assertEqual({key:saved[key] for key in profile},profile)
        self.call(path,'PUT',{'active':True,'can_edit':False,'can_publish':True})
        preserved=next(item for item in self.call('/api/admin/managers')[1] if item['id']==user['id'])
        self.assertEqual({key:preserved[key] for key in profile},profile)

    def test_profile_endpoint_does_not_change_manager_access(self):
        self.admin_login()
        user=next(item for item in self.call('/api/admin/managers')[1] if item['login']=='manager@example.test')
        path='/api/admin/managers/'+user['id']
        self.call(path,'PUT',{'active':True,'can_edit':False,'can_publish':False})
        profile={'firstName':'Анна','lastName':'Петрова','phone':'123','messengerPhone':'456','photo':'','messengers':[]}
        self.assertEqual(self.call(path+'/profile','PUT',{'profile':profile})[0],200)
        saved=next(item for item in self.call('/api/admin/managers')[1] if item['id']==user['id'])
        self.assertEqual({key:saved[key] for key in profile},profile)
        self.assertFalse(saved['can_edit'])
        self.assertFalse(saved['can_publish'])

    def test_manager_can_delete_own_proposal_with_links_and_submission(self):
        proposal_row,token=self.published()
        self.assertEqual(self.call('/api/public/'+token+'/submit','POST',{},False)[0],200)
        self.assertEqual(self.call('/api/proposals/'+proposal_row['id'],'DELETE')[0],200)
        self.assertEqual(self.call('/api/public/'+token,authenticated=False)[0],404)
        self.assertEqual(self.call('/api/proposals')[1],[])

    def test_admin_delete_manager_removes_account_and_owned_data(self):
        _,token=self.published()
        owner_login='manager@example.test'
        self.admin_login()
        user=next(item for item in self.call('/api/admin/managers')[1] if item['login']==owner_login)
        self.assertEqual(self.call('/api/admin/managers/'+user['id'],'DELETE')[0],200)
        self.assertFalse(any(item['id']==user['id'] for item in self.call('/api/admin/managers')[1]))
        self.assertEqual(self.call('/api/public/'+token,authenticated=False)[0],404)
        self.assertEqual(self.call('/api/login','POST',{'login':owner_login,'password':'long-test-password'})[0],401)

if __name__=='__main__':unittest.main()
