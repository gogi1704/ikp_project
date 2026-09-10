# Безопасное развёртывание на общем сервере

Целевой адрес: `https://kp.cheloveckmed.ru`. Корневой виртуальный хост `cheloveckmed.ru`, на котором работает MAX-бот, не изменяется. Приложение запускается отдельным Compose-проектом `cheloveckmed-ikp` и доступно на сервере только через `127.0.0.1:18080`.

## 1. Инвентаризация без изменений

На сервере сохранить текущее состояние:

```bash
sudo ss -ltnp
docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Status}}'
sudo nginx -T > "$HOME/nginx-before-ikp-$(date +%Y%m%d-%H%M%S).txt"
sudo test ! -e /etc/nginx/sites-enabled/kp.cheloveckmed.ru.conf
```

Если порт `18080` занят или конфигурация поддомена уже существует, остановиться и выбрать другой порт/проверить существующий сайт. Не редактировать конфигурацию `cheloveckmed.ru` и контейнер MAX-бота.

## 2. DNS

Создать A-запись `kp.cheloveckmed.ru` на IP сервера. На момент подготовки корневой домен указывал на `213.148.9.40`, но перед изменением DNS адрес нужно сверить с фактическим IP сервера.

## 3. Файлы приложения

Разместить проект отдельно, например в `/opt/cheloveckmed-ikp`. Не копировать локальные `.env`, `.venv`, `data`, `.idea` и тестовые базы. На сервере:

```bash
cd /opt/cheloveckmed-ikp
cp .env.production.example .env.production
chmod 600 .env.production
mkdir -p data backups
sudo chown -R 1000:1000 data backups
```

В `.env.production` установить настоящий `DADATA_API_KEY`. `PUBLIC_ORIGIN` должен остаться равным `https://kp.cheloveckmed.ru`.

## 4. Изолированный запуск

```bash
./deploy/preflight.sh
docker-compose -p cheloveckmed-ikp -f compose.production.yml build
docker-compose -p cheloveckmed-ikp -f compose.production.yml up -d
docker-compose -p cheloveckmed-ikp -f compose.production.yml ps
curl --fail http://127.0.0.1:18080/healthz
```

Создать первого администратора интерактивно:

```bash
docker-compose -p cheloveckmed-ikp -f compose.production.yml exec app python run.py --create-admin admin
```

## 5. Отдельный виртуальный хост Nginx

Файлы подключаются отдельно. Существующие сайты не заменяются:

```bash
sudo cp deploy/nginx/ikp-rate-limit.conf /etc/nginx/conf.d/cheloveckmed-ikp-rate-limit.conf
sudo cp deploy/nginx/kp.cheloveckmed.ru.conf /etc/nginx/sites-available/kp.cheloveckmed.ru.conf
sudo ln -s /etc/nginx/sites-available/kp.cheloveckmed.ru.conf /etc/nginx/sites-enabled/kp.cheloveckmed.ru.conf
sudo nginx -t
sudo systemctl reload nginx
```

Если `nginx -t` не проходит, Nginx не перезагружать; удалить только новый symlink и новый rate-limit файл, затем снова выполнить `nginx -t`.

После распространения DNS выпустить отдельный сертификат:

```bash
sudo certbot --nginx -d kp.cheloveckmed.ru
sudo nginx -t
```

## 6. Проверка

Проверить `/healthz`, `/admin`, вход администратора, создание тестового менеджера, вход менеджера, подсказки ИНН, создание и публикацию КП, открытие персональной ссылки в приватном окне и отправку заявки. Затем удалить тестовые данные через интерфейс.

## Обновление

Перед обновлением создать согласованную копию SQLite:

```bash
mkdir -p backups
docker-compose -p cheloveckmed-ikp -f compose.production.yml exec -T app python scripts/backup.py "/app/backups/backup-$(date +%Y%m%d-%H%M%S).sqlite3"
docker-compose -p cheloveckmed-ikp -f compose.production.yml build
docker-compose -p cheloveckmed-ikp -f compose.production.yml up -d
curl --fail http://127.0.0.1:18080/healthz
```

## Откат

При проблеме сначала вернуть предыдущий образ/каталог приложения и снова выполнить `docker-compose -p cheloveckmed-ikp ... up -d`. Чтобы убрать сайт из внешнего доступа, удалить только `/etc/nginx/sites-enabled/kp.cheloveckmed.ru.conf`, проверить `sudo nginx -t` и перезагрузить Nginx. Команду `docker-compose down -v` не использовать: `-v` удаляет данные.
