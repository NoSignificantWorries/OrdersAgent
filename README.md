# Email orders agent (Система обработки писем)

Автоматическая классификация входящих писем: фильтрует только запросы на стоимость и новые заявки клиентов. Запускает сценарии анализа вложений, стандартизации данных и создания готового Excel-файла.

**Цель**: Ускорить обработку в 5 раз, минимизировать ошибки.

## Функции
- Определение типа письма по содержимому.
- Запуск сценария для формирование файла из письма: анализ вложений, замена наименований по справочнику.
- Уточнение данных у оператора.
- Сохранение результата в таблицу.
- Роли: менеджеры (по своей почте), админы (все заявки).

## Структура:

```
.
├── interface/
│   ├── backend/
│   └── frontend/
│       ├── mail-client/            # веб-клиент для менеджеров
│       │   ├── app/
│       │   │   ├── main.py         # FastAPI-приложение
│       │   │   ├── config.py       # конфиг фронтового сервиса
│       │   │   ├── db.py           # подключение к БД
│       │   │   ├── routers/
│       │   │   │   ├── auth.py     # авторизация (Яндекс OAuth, сессии)
│       │   │   │   └── queue.py    # API очереди писем для UI
│       │   │   ├── services/
│       │   │   │   ├── users.py    # работа с пользователями
│       │   │   │   └── queue.py    # выборка/обновление очереди писем
│       │   │   ├── static/
│       │   │   │   ├── css/        # стили интерфейса менеджера
│       │   │   │   └── js/         # логика интерфейса (script.js)
│       │   │   └── templates/
│       │   │       ├── index.html  # основная страница с очередью писем
│       │   │       └── login.html  # страница логина
│       │   ├── .env
│       │   └── requirements.txt
│       ├── pages/                  # старый статичный прототип интерфейса
│       │   ├── index.html
│       │   ├── login.html
│       │   ├── main.html
│       │   └── components/
│       │       └── order_card.html
│       └── static/                 # статические ресурсы для старых страниц
│           ├── css/
│           │   ├── style.css
│           │   ├── login.css
│           │   ├── main.css
│           │   └── components/
│           │       └── order_card.css
│           └── js/
│               ├── main.js
│               ├── login.js
│               └── modules/
│                   └── order_card.js
├── llm_worker/                     # Python-воркер с моделью-классификатором
│   ├── main.py                     # запуск LLM-воркера
│   ├── logging_config.py
│   ├── config.json                 # конфиг LLM-воркера
│   ├── app.log                     # лог работы
│   ├── pyproject.toml
│   ├── uv.lock
│   └── llm/
│       ├── llm.py                  # обёртка над моделью / API
│       ├── train.py                # обучение классификатора
│       ├── analyze_training.py     # анализ качества/датасета
├── mail/
│   ├── cmd/
│   │   └── mail-agent/
│   │       └── main.go             # запуск агента чтения почты
│   └── internal/
│       ├── config/
│       │   ├── config.go           # загрузка config.json
│       ├── client/
│       │   └── client.go           # IMAP-клиент (подключение к почтовому ящику)
│       ├── parser/
│       │   └── email.go            # парсинг писем и вложений
│       ├── storage/
│       │   ├── dataset_repo.go     # сохранение писем в датасет
│       │   └── repo.go             # запись в основное хранилище/БД
│       └── orders/
│           └── processor.go        # обработка письма, связь с LLM и storage
├── storage/
│   ├── api/
│   │   ├── db.go                   # подключение к БД
│   │   └── repo.go                 # методы доступа к данным для других сервисов
│   ├── cmd/
│   │   └── api/
│   │       └── main.go             # REST API поверх хранилища
│   ├── configdb/
│   │   └── configdb.go             # конфигурация базы
│   ├── init/
│   │   ├── 01-schema.sql           # базовая схема БД
│   │   └── 02-functions.sql        # функции/процедуры в БД
│   ├── internal/
│   ├── .env.example
│   └── docker-compose.yml
├── table_worker/
├── go.mod
├── go.sum
```

Проект в разработке.

## Запуск

1. LLM-воркер (классификатор писем)

```
cd llm_worker
uv run python main.py
```

2. Веб-интерфейс (FastAPI + фронт)

```
cd interface/frontend/mail-client
venv\Scripts\activate
uvicorn app.main:app
```

По умолчанию интерфейс будет доступен на http://localhost:8000/.

Подробнее в README в папке `interface/frontend/mail-client`

3. Почтовый агент (Go-сервис, который читает почту)

```
cd <корень репозитория>
go run ./mail/cmd/mail-agent --user-id=2
```

--user-id — id пользователя в БД, для которого агент будет забирать письма и класть их в очередь.