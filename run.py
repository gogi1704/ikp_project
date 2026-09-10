import argparse
import getpass
from backend.app import application, init_db, create_user

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    accounts = parser.add_mutually_exclusive_group()
    accounts.add_argument('--create-user', metavar='LOGIN')
    accounts.add_argument('--create-admin', metavar='LOGIN')
    parser.add_argument('--dev', action='store_true')
    args = parser.parse_args()
    init_db()
    if args.create_user or args.create_admin:
        create_user(args.create_user or args.create_admin, getpass.getpass('Пароль (минимум 12 символов): '), 'admin' if args.create_admin else 'manager')
        print('Администратор создан' if args.create_admin else 'Менеджер создан')
    elif args.dev:
        from wsgiref.simple_server import make_server
        print('http://localhost:8000/manager', flush=True)
        make_server('127.0.0.1', 8000, application).serve_forever()
    else:
        from waitress import serve
        serve(application, host='0.0.0.0', port=8000, threads=8, max_request_body_size=500000)
