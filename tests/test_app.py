import io
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from backend import app
from backend.domain import proposal, selection, calculate

class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        app.DB=str(Path(self.tmp.name)/'test.sqlite3')
        app.init_db()
        app.create_user('manager@example.test','long-test-password')
        self.cookie=''
        self.csrf=''
        self.call('/api/login','POST',{'login':'manager@example.test','password':'long-test-password'})

    def tearDown(self):
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

    def test_full_flow_snapshot_and_idempotency(self):
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
        self.assertEqual(result['totals']['total'],3850000)
        duplicate=self.call(endpoint+'/submit','POST',s,False)[1]
        self.assertEqual(result['receipt'],duplicate['receipt'])
        self.assertEqual(len(self.call('/api/proposals/'+p['id']+'/activity')[1]['submissions']),1)
        overview=self.call('/api/activity')[1]
        self.assertEqual((overview['linkCount'],overview['submissionCount']),(1,1))
        self.assertEqual(overview['proposals'][0]['id'],p['id'])
        self.assertEqual(overview['proposals'][0]['submissions'][0]['id'],result['receipt'])

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

    def test_links_ignore_expiry_but_respect_revocation(self):
        p,token=self.published()
        self.assertEqual(self.call('/api/proposals/'+p['id'],'PUT',{'body':p['body'],'version':0})[0],409)
        with app.connect() as db: db.execute('UPDATE links SET expires=0')
        self.assertEqual(self.call('/api/public/'+token,authenticated=False)[0],200)
        lid=self.call('/api/proposals/'+p['id']+'/activity')[1]['links'][0]['id']
        self.assertEqual(self.call('/api/proposals/'+p['id']+'/revoke','POST',{'id':lid})[0],200)
        self.assertEqual(self.call('/api/public/'+token,authenticated=False)[0],410)

    def test_validation_and_price_integrity(self):
        for value in [-1,1.5,True,100001]:
            self.assertEqual(self.call('/api/proposals','POST',{'count':value})[0],400)
        p=proposal({'count':10,'corp':{'delay':{'on':False,'price':0}}})
        s=selection(p)
        s['corp']['delay']['on']=True
        with self.assertRaises(ValueError):selection(p,s)
        s=selection(p);s['addons']['lmk']['qty']=11
        with self.assertRaises(ValueError):selection(p,s)
        p=proposal({'count':1,'basePrice':0.29})
        s=selection(p)
        self.assertEqual(calculate(p,s)['base'],29)
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
        app.create_user('admin@example.test','admin-test-password',role='admin')
        self.assertEqual(self.call('/api/login','POST',{'login':'admin@example.test','password':'admin-test-password'})[0],200)

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
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],4)

    def test_manager_profile_is_copied_to_new_proposals(self):
        self.admin_login()
        profile={'firstName':'Лариса','lastName':'Захарченко','phone':'+7 863 322-67-66','messengerPhone':'+7 989 506-74-60','photo':''}
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

    def test_admin_updates_and_preserves_manager_profile(self):
        self.admin_login()
        managers=self.call('/api/admin/managers')[1]
        user=next(item for item in managers if item['login']=='manager@example.test')
        profile={'firstName':'Иван','lastName':'Иванов','phone':'+7 900 111-22-33','messengerPhone':'@ivanov','photo':''}
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
        profile={'firstName':'Анна','lastName':'Петрова','phone':'123','messengerPhone':'456','photo':''}
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
