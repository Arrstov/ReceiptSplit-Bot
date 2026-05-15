# ReceiptSplit Bot MVP

Базовый, но рабочий MVP проекта Telegram-бота с поддержкой Telegram Mini App для сценария ReceiptSplit.

В этом проекте есть:

* `aiogram`-бот, который отвечает на `/start`
* inline-кнопка `Открыть приложение` с `web_app`
* `FastAPI` backend, который раздаёт Mini App и принимает данные из него
* HTML/CSS/JS Mini App, открывающийся внутри Telegram
* загрузка фото чека и извлечение QR-кода на backend
* попытка получить позиции чека через `proverkacheka.com`
* отправка результата обратно пользователю в чат

---

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

* поиск QR-кода на фотографии
* извлечение даты, суммы, ФН, ФД и ФП
* вывод результата в Mini App
* отправка результата пользователю в Telegram

Важно:

* QR на кассовом чеке обычно содержит только реквизиты чека
* для полного состава товаров нужен внешний источник данных
* в текущем проекте для этого добавлена интеграция с `proverkacheka.com`

---

## Стек

* Python 3.11+
* aiogram 3
* FastAPI
* HTML + CSS + JavaScript
* `.env` для конфигурации

---

## Что нужно заранее

* Python 3.11+ установлен в системе
* Python добавлен в `PATH`
* Telegram-бот создан через BotFather
* Доступен публичный HTTPS URL для Mini App

Если команды `python` или `pip` не находятся, переустановите Python с официального сайта и включите опцию `Add Python to PATH`.

---

## Структура проекта

```text
ReceiptSplit-Bot/
├─ backend/
│  ├─ __init__.py
│  ├─ main.py
│  ├─ mvp_store.py
│  ├─ receipt_ocr.py
│  ├─ qr_decoder.py
│  ├─ receipt_qr.py
│  └─ proverkacheka_client.py
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
├─ data/
│  └─ mvp.sqlite3
├─ .env.example
├─ .gitignore
├─ README.md
└─ requirements.txt
```

---

## Переменные окружения

Создайте файл `.env` в корне проекта и заполните его по примеру `.env.example`.

Используемые переменные:

* `BOT_TOKEN` — токен Telegram-бота от BotFather
* `WEBAPP_URL` — публичный HTTPS URL для Mini App
* `BACKEND_HOST` — хост для локального запуска FastAPI
* `BACKEND_PORT` — порт для локального запуска FastAPI
* `LOG_LEVEL` — уровень логирования
* `INIT_DATA_TTL_SECONDS` — максимальный возраст `initData` в секундах
* `PROVERKACHEKA_API_TOKEN` — токен доступа к API `proverkacheka.com`
* `PROVERKACHEKA_API_URL` — URL API сервиса проверки чеков
* `PROVERKACHEKA_TIMEOUT_SECONDS` — таймаут внешнего API в секундах

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

---

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

Заполните обязательные поля: `BOT_TOKEN`, `WEBAPP_URL`, `PROVERKACHEKA_API_TOKEN`.

### 4. Запустите backend

```powershell
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

* Mini App: `http://127.0.0.1:8000/`
* Healthcheck: `http://127.0.0.1:8000/api/health`

### 5. Запустите бота

В отдельном терминале:

```powershell
python -m bot.main
```

---

## Как подключить URL Mini App

* URL Mini App берётся из переменной окружения `WEBAPP_URL`
* Бот передаёт его в inline-кнопку:

```python
InlineKeyboardButton(text="Открыть приложение", web_app=WebAppInfo(url=WEBAPP_URL))
```

**Важно:** для работы в Telegram нужен публичный HTTPS URL. `http://localhost` не работает в основном Telegram-клиенте.

---

## Использование ngrok

1. Установите `ngrok`
2. Запустите backend на `8000`
3. В новом терминале:

```powershell
ngrok http 8000
```

4. Скопируйте HTTPS адрес вида `https://abc123.ngrok-free.app`
5. Укажите его в `.env` как `WEBAPP_URL`
6. Перезапустите backend и бота

Альтернативы: Cloudflare Tunnel, localhost.run или VPS с HTTPS.

---

## OCR и обработка чеков

* OpenCV ищет QR-код на фото чека
* Из QR извлекаются реквизиты: дата, сумма, ФН, ФД, ФП
* Запрос к внешнему сервису `proverkacheka.com` получает позиции чека
* Если API недоступен — используется локальный OCR Tesseract
* Результат сохраняется в базе и отображается в Mini App

---

## Ограничения и рекомендации

* QR-код содержит только реквизиты чека — полный список товаров требует API или ручного ввода
* SQLite достаточен для MVP, PostgreSQL для масштабирования
* Минимальный UX — простой интерфейс Mini App
* Основной фокус — рабочий сценарий дележа чеков, монетизация и расширенные функции — в будущем

---

## Почему выбран этот подход

* Данные Mini App отправляются через backend для валидации `initData`
* Backend позволяет расширять OCR, хранение сессий и расчёты
* inline web_app удобен для интеграции в Telegram без отдельного приложения

---

## Следующие шаги развития

1. Хранение пользовательских сессий в SQLite
2. Сценарий `/split` для группового чата
3. Добавление участников и создание событий
4. Загрузка фото чека и интеграция с OCR
5. Список позиций и распределение между участниками
6. Итоговые суммы и история сессий
7. Расширение Mini App до полноценного интерфейса управления чеком
