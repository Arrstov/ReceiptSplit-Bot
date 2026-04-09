# ReceiptSplit Bot MVP

Базовый, но рабочий MVP проекта Telegram-бота с поддержкой Telegram Mini App для сценария ReceiptSplit.

В этом проекте есть:

- `aiogram`-бот, который отвечает на `/start`
- inline-кнопка `Открыть приложение` с `web_app`
- `FastAPI` backend, который раздаёт Mini App и принимает данные из него
- HTML/CSS/JS Mini App, открывающийся внутри Telegram
- загрузка фото чека и извлечение QR-кода на backend
- попытка получить позиции чека через `proverkacheka.com`
- отправка результата обратно пользователю в чат

## Что делает MVP

Текущий сценарий работы:

1. Пользователь пишет боту `/start`
2. Бот отправляет сообщение с inline-кнопкой `Открыть приложение`
3. По кнопке внутри Telegram открывается Mini App
4. Пользователь загружает фотографию чека
5. Mini App отправляет фото на backend
6. Backend пытается найти QR-код на изображении
7. Backend разбирает реквизиты чека из QR
8. Backend пытается получить позиции чека через `proverkacheka.com`
9. Backend отправляет результат пользователю обратно в чат с ботом

Что уже умеет обработка:

- поиск QR-кода на фотографии
- извлечение даты, суммы, ФН, ФД и ФП
- вывод результата в Mini App
- отправка результата пользователю в Telegram

Важно:

- QR на кассовом чеке обычно содержит только реквизиты чека
- для полного состава товаров нужен внешний источник данных
- в текущем проекте для этого добавлена интеграция с `proverkacheka.com`

## Стек

- Python
- aiogram
- FastAPI
- HTML + CSS + JavaScript
- `.env` для конфигурации

## Что нужно заранее

- Python 3.11+ установлен в системе
- Python добавлен в `PATH`
- Telegram-бот создан через BotFather
- доступен публичный HTTPS URL для Mini App

Если команды `python` или `pip` не находятся, переустановите Python с официального сайта и включите опцию `Add Python to PATH`.

## Структура проекта

```text
ReceiptSplit-Bot/
├─ backend/
│  ├─ __init__.py
│  └─ main.py
├─ bot/
│  ├─ __init__.py
│  └─ main.py
├─ common/
│  ├─ __init__.py
│  ├─ config.py
│  └─ telegram_auth.py
├─ webapp/
│  ├─ app.js
│  ├─ index.html
│  └─ styles.css
├─ .env.example
├─ .gitignore
├─ README.md
└─ requirements.txt
```

## Переменные окружения

Создайте файл `.env` в корне проекта и заполните его по примеру `.env.example`.

Используемые переменные:

- `BOT_TOKEN` — токен Telegram-бота от BotFather
- `WEBAPP_URL` — публичный HTTPS URL, по которому Telegram сможет открыть Mini App
- `BACKEND_HOST` — хост для локального запуска FastAPI
- `BACKEND_PORT` — порт для локального запуска FastAPI
- `LOG_LEVEL` — уровень логирования
- `INIT_DATA_TTL_SECONDS` — максимальный возраст `initData` в секундах
- `PROVERKACHEKA_API_TOKEN` — токен доступа к API `proverkacheka.com`
- `PROVERKACHEKA_API_URL` — URL API сервиса проверки чеков
- `PROVERKACHEKA_TIMEOUT_SECONDS` — таймаут внешнего API в секундах

Пример:

```env
BOT_TOKEN=123456:ABCDEF_your_token
WEBAPP_URL=https://your-ngrok-domain.ngrok-free.app
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
LOG_LEVEL=INFO
INIT_DATA_TTL_SECONDS=86400
PROVERKACHEKA_API_TOKEN=your_proverkacheka_api_token_here
PROVERKACHEKA_API_URL=https://proverkacheka.com/api/v1/check/get
PROVERKACHEKA_TIMEOUT_SECONDS=20
```

## Как создать бота через BotFather

1. Откройте Telegram и найдите `@BotFather`
2. Отправьте команду `/newbot`
3. Укажите имя бота
4. Укажите уникальный username, который заканчивается на `bot`
5. Скопируйте выданный токен
6. Вставьте токен в `.env` в переменную `BOT_TOKEN`

Опционально:

- если хотите, чтобы Mini App открывался ещё и с профиля бота или через меню, настройте это в `@BotFather`
- для текущего MVP это не обязательно, потому что запуск уже работает через inline-кнопку `web_app`

## Установка и запуск

### 1. Создайте виртуальное окружение

PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Установите зависимости

```powershell
pip install -r requirements.txt
```

### 3. Создайте `.env`

```powershell
Copy-Item .env.example .env
```

После этого заполните:

- `BOT_TOKEN`
- `WEBAPP_URL`
- `PROVERKACHEKA_API_TOKEN`

### 4. Запустите backend

```powershell
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

После запуска локально откроются:

- Mini App: `http://127.0.0.1:8000/`
- healthcheck: `http://127.0.0.1:8000/api/health`

### 5. Запустите бота

В отдельном терминале:

```powershell
python -m bot.main
```

## Как подключить URL Mini App

Для этого MVP URL Mini App берётся из переменной окружения `WEBAPP_URL`.

Именно этот URL бот передаёт в inline-кнопку:

- `InlineKeyboardButton`
- `web_app=WebAppInfo(url=WEBAPP_URL)`

Что нужно сделать:

1. Поднимите backend локально
2. Пробросьте локальный сервер наружу в публичный HTTPS URL
3. Скопируйте этот URL в `.env` как `WEBAPP_URL`
4. Перезапустите backend и бота

Важно:

- для обычного Telegram нужен публичный `HTTPS` URL
- `http://localhost:8000` внутри обычного Telegram работать как полноценный Mini App не будет
- локальный URL можно открыть в браузере для проверки вёрстки, но не для полной проверки Telegram-интеграции

## Как использовать ngrok

Пример с `ngrok`:

1. Установите `ngrok`
2. Запустите backend локально на `8000`
3. В новом окне терминала выполните:

```powershell
ngrok http 8000
```

4. Скопируйте HTTPS адрес вида:

```text
https://abc123.ngrok-free.app
```

5. Укажите его в `.env`:

```env
WEBAPP_URL=https://abc123.ngrok-free.app
```

6. Перезапустите бота

Альтернативы:

- Cloudflare Tunnel
- localhost.run
- любой VPS или хостинг с HTTPS

## Как протестировать внутри Telegram

Для полной проверки нужен именно Telegram-клиент:

1. Запустите backend
2. Запустите бота
3. Убедитесь, что `WEBAPP_URL` указывает на публичный HTTPS URL
4. Откройте чат с ботом в Telegram
5. Отправьте `/start`
6. Нажмите `Открыть приложение`
7. Убедитесь, что открывается встроенное окно Mini App
8. Введите название чека
9. Нажмите `Отправить в бота`
10. Проверьте, что бот прислал ответ в чат

Что отображается в Mini App:

- заголовок
- краткий текст
- форма с одним полем
- кнопка действия
- данные о пользователе, если Mini App открыт внутри Telegram
- статус `initData`

## Ограничения локального запуска

- обычный локальный браузер не передаёт `Telegram.WebApp.initData`
- без Telegram нельзя полноценно проверить встроенное открытие окна
- без публичного HTTPS URL Telegram-клиент не сможет нормально работать с Mini App в основной среде
- reply keyboard и inline button используют немного разные сценарии возврата данных

Для текущего MVP выбран самый простой рабочий вариант:

- открытие через inline-кнопку
- возврат данных через backend
- отправка результата обратно пользователю ботом

## Почему сделано именно так

В Telegram Mini Apps есть два популярных варианта возврата данных:

1. `Telegram.WebApp.sendData(...)`
2. отправка данных на backend

Для этого MVP основной путь — backend, потому что:

- он хорошо подходит для `inline web_app`
- позволяет валидировать `initData`
- даёт основу для будущей серверной логики ReceiptSplit
- его проще расширять под OCR, сессии, базу данных и расчёты

## Что уже реализовано в коде

### Бот

- обработка `/start`
- inline-кнопка `Открыть приложение`
- обработчик `web_app_data` для запасного сценария с `sendData`

### Backend

- раздача статических файлов Mini App
- endpoint `/api/health`
- endpoint `/api/receipts/process-photo`
- проверка подписи `initData`
- распознавание QR-кода на фотографии
- запрос к `proverkacheka.com` по `qrraw` или `qrfile`
- попытка достать список позиций из ответа API
- отправка сообщения пользователю через Telegram Bot API

### Mini App

- подключение `telegram-web-app.js`
- вызов `Telegram.WebApp.ready()`
- вызов `Telegram.WebApp.expand()`
- чтение `initDataUnsafe.user`
- загрузка фото чека
- отправка фотографии на backend
- базовая обработка ошибок
- мобильная адаптация

## Что вручную нужно заполнить вам

- токен бота в `.env`
- публичный `WEBAPP_URL` в `.env`
- токен `PROVERKACHEKA_API_TOKEN` в `.env`
- при необходимости имя и username бота через BotFather

## Логичные следующие шаги развития проекта

1. Добавить SQLite и хранение пользовательских сессий
2. Сделать сценарий `/split` для группового чата
3. Добавить создание сессии дележа и список участников
4. Добавить загрузку фото чека
5. Подключить OCR
6. Реализовать список позиций и распределение по участникам
7. Добавить итоговые суммы и историю сессий
8. Перенести форму Mini App в полноценный интерфейс управления чеком

## Полезные замечания

- Если бот не отвечает, проверьте корректность `BOT_TOKEN`
- Если Mini App не открывается, проверьте `WEBAPP_URL` и доступность HTTPS
- Если backend пишет ошибку проверки `initData`, скорее всего приложение открыто не внутри Telegram или используется неверный токен

## Полезные официальные ссылки

- Telegram Mini Apps: https://core.telegram.org/bots/webapps
- Telegram Bot API: https://core.telegram.org/bots/api
