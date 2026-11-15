# AI-скаут

Сервис мониторинга Telegram-источников: слушает выбранные чаты, сохраняет найденные сообщения
в SQLite и печатает их в консоль. Задуман как полуавтоматический лидогенератор для фрилансера:
ИИ готовит черновик отклика, а карточку заказа бот присылает в личку — ответ клиенту всегда
отправляет человек.

**Статус.** Ядро (этап 1) работает: сбор сообщений, дедупликация и запись в SQLite проверены
12 тестами и сквозным прогоном на фикстурах. Чего в коде ещё нет — честно перечислено в разделе
«Что описано в конфиге и архитектуре, но не реализовано» ниже.

## Что делает проект

1. `scripts/login.py` один раз авторизует userbot-аккаунт и сохраняет Telethon-сессию в `data/`.
2. `python -m ai_scout` поднимает Telethon-клиент и подписывается на `events.NewMessage` с
   `incoming=True` — на чаты из `config/settings.yaml`, на все входящие (`--all`) или перечисленные
   через `--chat`. Пересылки и сообщения от ботов отбрасываются по флагам `ignore_forwards` и
   `ignore_bots`.
3. Прошедшее сообщение превращается в `RawMessage`, сохраняется в SQLite (`data/scout.db`) и
   выводится в консоль со ссылкой на оригинал. Дедупликация — по ключу `(chat_id, message_id)`:
   повтор сохраняется один раз, затем логируется `message_duplicate`.

Ссылки строит `telegram/resolver.py`: публичный чат → `https://t.me/<username>/<id>`, приватная
супергруппа → `https://t.me/c/<id>/<id>`, личный диалог → `tg://openmessage?user_id=<id>`; для
обычной группы без username ссылки нет. ИИ в этом потоке не участвует: ни вызовов LLM, ни фильтра
по ключевым словам, ни отправки карточек в основном коде нет — это заготовки следующих этапов.

## Что описано в конфиге и архитектуре, но не реализовано

- `filters.whitelist` / `stopwords` / `min_length` / `max_length` — префильтра в ядре нет; свои
  хардкод-списки слов есть только внутри черновых скриптов.
- `ai.*` (`claude-sonnet-4-5`, `max_difficulty`, `daily_budget_usd`) — обращений к Claude нет
  вообще; `anthropic` не входит в базовые зависимости и в `.venv` не установлен.
- `pipeline.queue_size` / `workers` — очереди и воркеров нет, обработчик вызывается прямо из события.
- Колонки `difficulty`, `fit`, `verdict_json`, `draft_reply`, `sent_at` в `leads` всегда пустые,
  `status` всегда `received`; карточки ботом не отправляются (нет ни `aiogram`, ни Bot API).
- `ARCHITECTURE.md` описывает будущие модули (`filters/`, `ai/`, `pipeline/`, `telegram/bot.py`,
  `config/prompts/`), которых в `src/` нет. Настройки — не то же самое, что реализация.

## Технологический стек

| Что | Чем | Версия |
|---|---|---|
| Язык | Python | `>=3.11` (в `.venv` — 3.12.16) |
| Telegram | `telethon` | `>=1.36,<2` (1.45.0) |
| Модели и конфиг | `pydantic` + `pydantic-settings` | `>=2.7,<3` / `>=2.3,<3` (2.14.2) |
| СУБД | SQLite через `aiosqlite`, WAL, миграции по `PRAGMA user_version` | `>=0.20,<1` |
| YAML и логи | `PyYAML`; `structlog`: цветная консоль или JSON | `>=6.0,<7`; `>=24.1,<26` (25.5.0) |
| Сборка | setuptools, `pip install -e .`, entrypoint `ai-scout` | — |
| Опционально | `anthropic` (extra `ai`); `pytest`, `pytest-asyncio`, `ruff` (extra `dev`) | см. `pyproject.toml` |

`httpx`, нужный `ai.py`, `mock_run.py` и `web_scout.py`, в `pyproject.toml` **не объявлен** и в
текущем `.venv` отсутствует; `aiogram` из бэклога тоже не подключён.

## Установка

```powershell
uv venv --python 3.12 .venv
.\.venv\Scripts\Activate.ps1
uv pip install -e ".[dev]"
```

Без `uv`: `python -m venv .venv`, активировать тем же скриптом, затем `python -m pip install
--upgrade pip` и `python -m pip install -e ".[dev]"`. Если PowerShell не даёт активировать
окружение: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`. Черновым скриптам нужен
ещё `httpx`: `pip install httpx`.

## Настройка

### 1. Секреты в `.env`

Создайте файл из шаблона (`Copy-Item .env.example .env`) и заполните переменные:

| Переменная | Обязательна | Что это и где взять |
|---|---|---|
| `TELEGRAM_API_ID` | да | Числовой `api_id` аккаунта: [my.telegram.org](https://my.telegram.org) → API development tools |
| `TELEGRAM_API_HASH` | да | `api_hash` оттуда же; проверяется длина не меньше 8 символов |
| `TELEGRAM_PHONE` | да для `login.py` | Номер в международном формате (`+79990000000`); без него логин откажется работать |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_NOTIFY_CHAT_ID` | нет | Токен бота от [@BotFather](https://t.me/BotFather) и ID чата для карточек — нужны только `mock_run.py` и `web_scout.py`; пустой ID `mock_run.py` попробует найти через `getUpdates` |
| `ANTHROPIC_API_KEY` | нет | Ключ Anthropic; скрипты кладут его в `AIService.api_key`, хотя фактически `ai.py` обращается к DeepSeek |

Пустые строки для необязательных переменных допустимы — `config.py` превращает их в `None`.
Валидация строгая: без `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` или при опечатке в имени ключа в
`settings.yaml` запуск падает с понятным сообщением вместо трейсбека.

### 2. Чаты в `config/settings.yaml`

В секции `telegram` укажите `source_chats` — список `@username` публичных чатов или числовых ID
вида `-1001234567890`. По умолчанию список пуст — тогда запускайте с `--all` или `--chat`. Ядро
читает отсюда `session_path`, `source_chats`, `ignore_forwards`, `ignore_bots`, `catch_up` (при
`false` подтягивается только то, что пришло после запуска), `storage.db_path`, `logging.level`,
`logging.json_logs`; относительные пути считаются от корня проекта. Блоки `filters`, `ai`,
`pipeline` валидируются, но не используются. Путь к конфигу переопределяется переменной
`AI_SCOUT_CONFIG` или флагом `--config`.

### 3. Первичная авторизация

`python scripts/login.py` — код придёт в Telegram, при двухфакторной защите пароль спросят через
`getpass`. Сессия сохраняется как `data/scout_session.session`, номер берётся из `TELEGRAM_PHONE`.

## Запуск

```powershell
python -m ai_scout                 # чаты из config/settings.yaml
ai-scout                           # то же через entrypoint после установки пакета
python -m ai_scout --all           # слушать все входящие (для первого теста)
python -m ai_scout --chat @freelance_chat --chat -1001234567890   # флаг повторяемый
python -m ai_scout --all --log-level DEBUG   # подробные логи (есть ещё --json-logs)
python -m ai_scout --config C:\path\to\settings.yaml
```

Остановка — `Ctrl+C`. Без сессии процесс завершается с кодом 2 и подсказкой `scripts/login.py`;
без чатов и без `--all` — тоже код 2.

## Скрипты

- `scripts/login.py` — одноразовый вход в Telegram, создаёт `data/scout_session.session`; читает
  `.env` вручную, без `pydantic-settings`. Запускается.
- `scripts/replay.py` — прогоняет `tests/fixtures/messages.json` через настоящий `MessageHandler`,
  `LeadRepository` и SQLite, без Telegram, `.env` и сети; ключи `--reset`, `--db :memory:`,
  `--fixture`, `--keep-forwards`, `--keep-bots`. Проверен: на фикстурах проходит 7 сценариев —
  3 сохранено, 1 дубль, 3 пропущено (пересылка, бот, медиа без текста).
- `scripts/mock_run.py` — симуляция: 3 захардкоженных заказа → свои стоп-слова и триггеры →
  отклик → карточка ботом; создаёт таблицу `leads` собственным SQL. Нужен `httpx`.
- `scripts/web_scout.py` — парсит открытую веб-ленту `t.me/s/<channel>` регулярками, берёт 10
  последних постов, фильтрует по стоп-словам и шлёт карточку ботом. Ссылается на неопределённую
  `ALLOWED_WORDS`, поэтому не запустится; нужен `httpx`.

## Структура проекта

```text
AI_scout/
├─ pyproject.toml            # зависимости, extras, entrypoint ai-scout, настройки pytest и ruff
├─ BACKLOG.md                # бэклог M-001: цель, объём MVP, критерии приёмки
├─ .env.example              # шаблон секретов
├─ config/settings.yaml      # чаты, хранилище, логи, заготовки filters/ai/pipeline
├─ docs/ai-scout/ARCHITECTURE.md   # проектная архитектура, частично про будущие этапы
├─ scripts/
│  ├─ login.py               # авторизация в Telegram
│  ├─ replay.py              # прогон фикстур без сети
│  ├─ mock_run.py            # симуляция пайплайна на захардкоженных сообщениях
│  ├─ web_scout.py           # парсер веб-лент публичных каналов (сломан)
│  └─ scripts/login.py       # мусорный дубль, не используется
├─ src/ai_scout/
│  ├─ __main__.py / main.py  # точка входа python -m ai_scout и CLI (--config/--chat/--all/логи)
│  ├─ config.py              # YAML + .env → типизированный AppConfig, строгая валидация
│  ├─ logging.py             # structlog: цветная консоль или JSON, UTF-8 вывод в Windows
│  ├─ models.py              # RawMessage (frozen) и LeadStatus
│  ├─ ai.py                  # черновик генерации отклика через DeepSeek; ядру не подключён
│  ├─ telegram/              # listener.py, handler.py, resolver.py, fakes.py
│  └─ storage/               # db.py (aiosqlite, WAL, миграции) и repository.py (сохранение, дедуп)
├─ tests/                    # 12 тестов + fixtures/messages.json (7 сценариев)
└─ data/                     # SQLite и сессии Telethon, в git не попадает
```

Пакет `telegram/`: `listener.py` — подписка на события Telethon и резолв чатов, `handler.py` —
событие в `RawMessage` без зависимости от Telethon, `resolver.py` — ссылки, `fakes.py` — fake-события.

## Тесты

```powershell
.\.venv\Scripts\Activate.ps1
pytest              # 12 тестов: test_config (3), test_handler (4), test_resolver (4), test_storage (1)
ruff check .        # линтер, line-length = 100
```

Асинхронные тесты идут в режиме `asyncio_mode = auto`, каталог `src` подхватывается через
`pythonpath` из `pyproject.toml`. 8 тестов используют фикстуру `tmp_path`, поэтому им нужен
доступный для записи каталог временных файлов. Фикстуры (`tests/fixtures/messages.json`: лиды,
дубль, пересылка, бот, медиа без текста, личка) общие для тестов и replay.
Все 12 тестов проходят.

## Известные проблемы

- `scripts/web_scout.py` использует `ALLOWED_WORDS`, которой нет ни в этом файле, ни где-либо ещё,
  — гарантированный `NameError` на первом подходящем посте.
- `src/ai_scout/ai.py` держит ключ-заглушку (`"используй_свой_ключ"`) прямо в конструкторе и ходит
  в `https://api.deepseek.com` с моделью `deepseek-chat`, хотя конфиг и `.env.example` говорят про
  Anthropic. Ядру файл не подключён.
- `scripts/scripts/login.py` — устаревший дубль: обращается к несуществующим атрибутам
  `config.telegram.api_id/api_hash/phone` (в коде они в `config.secrets`), вызывает `load_config()`
  без аргументов и хардкодит MTProto-прокси.
- Пути сессий расходятся: `login.py` пишет `data/scout_session.session`, ядро ждёт
  `data/scout.session`. Оба файла секретны.

## Безопасность

- `.env`, сессии Telethon (`data/*.session`) и базы (`data/*.db`) перечислены в `.gitignore`.
- Читаются только те чаты, где аккаунт уже состоит; массовых действий и рассылок нет.
- Автоотправка откликов клиентам не реализована и не входит в MVP: черновик отправляет человек.
- Файл сессии равнозначен доступу к аккаунту — не копируйте его в репозиторий и не передавайте.
