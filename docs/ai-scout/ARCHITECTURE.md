# AI-скаут — архитектура

Статус: draft · Связанная запись бэклога: [`M-001`](../../BACKLOG.md)

## 1. Что делает модуль

```
Telegram-чаты
     │  (Telethon, realtime)
     ▼
[Listener] ──► [Prefilter] ──► [Queue] ──► [Claude worker] ──► [Card builder] ──► [Bot] ──► закрытый чат
                    │                                                      
                    └─ мусор: в лог/статистику, без вызова LLM
```

Ключевая идея: **дешёвое сито до LLM**. В Claude уходит только текст, прошедший
белый список и не содержащий стоп-слов. LLM не решает «лид или нет» с нуля —
он оценивает сложность и пишет черновик.

## 2. Дерево файлов

```
ai-scout/
├─ pyproject.toml                 # зависимости, ruff, pytest, entrypoint
├─ README.md                      # быстрый старт
├─ .env.example                   # TELEGRAM_API_ID/HASH, BOT_TOKEN, ANTHROPIC_API_KEY
├─ .gitignore                     # .env, data/*.session, data/*.db, __pycache__
├─ config/
│  ├─ settings.yaml               # чаты, фильтры, лимиты, модель
│  └─ prompts/
│     ├─ system.md                # роль, стек, правила оценки
│     └─ schema.json              # JSON-схема ответа Claude
├─ src/ai_scout/
│  ├─ __init__.py
│  ├─ main.py                     # сборка приложения, graceful shutdown
│  ├─ config.py                   # pydantic-settings + YAML, типизированный конфиг
│  ├─ logging.py                  # structlog/loguru, JSON-логи
│  ├─ models.py                   # RawMessage, Lead, Verdict, LeadCard
│  ├─ telegram/
│  │  ├─ listener.py              # Telethon client, events.NewMessage
│  │  ├─ handler.py               # событие -> RawMessage -> SQLite (без Telethon)
│  │  ├─ fakes.py                 # fake-события для тестов/replay
│  │  ├─ resolver.py              # chat/message -> ссылка на клиента
│  │  └─ bot.py                   # aiogram Bot, send_card(), /stats
│  ├─ filters/
│  │  ├─ normalize.py             # lowercase, ё→е, пробелы, emoji, пунктуация
│  │  ├─ keywords.py              # whitelist/stopword, границы слов, веса
│  │  └─ pipeline.py              # цепочка правил -> FilterResult
│  ├─ ai/
│  │  ├─ claude.py                # Anthropic client, retries, budget, semaphore
│  │  ├─ prompts.py               # рендер шаблонов + few-shot
│  │  └─ schema.py                # pydantic-модель Verdict + JSON schema
│  ├─ pipeline/
│  │  ├─ queue.py                 # asyncio.Queue + N воркеров
│  │  └─ processor.py             # оркестрация: filter → AI → card → send
│  ├─ storage/
│  │  ├─ db.py                    # aiosqlite, миграции
│  │  └─ repository.py            # dedupe, save_lead, update_status
│  └─ utils/
│     ├─ text.py                  # обрезка, экранирование HTML
│     └─ backoff.py               # retry/FloodWait
├─ tests/
│  ├─ test_normalize.py
│  ├─ test_keywords.py
│  ├─ test_resolver.py
│  ├─ test_processor.py           # mock Claude + mock bot
│  └─ fixtures/messages.json      # реальные примеры «лид / мусор»
├─ scripts/
│  ├─ login.py                    # одноразовое создание Telethon-сессии
│  └─ replay.py                   # прогон фикстур через пайплайн (dry-run)
└─ data/                          # gitignored
   ├─ scout.session
   └─ scout.db
```

Почему так: `telegram/`, `filters/`, `ai/`, `pipeline/`, `storage/` — независимые
слои. Фильтры и промпты тестируются без сети, Claude и Telethon заменяются моками.

## 3. Модель данных

```python
class RawMessage(BaseModel):
    chat_id: int
    chat_title: str
    message_id: int
    sender_id: int | None
    sender_username: str | None
    sender_name: str | None
    text: str
    date: datetime
    link: str | None

class Verdict(BaseModel):
    difficulty: int          # 1..5
    fit: Literal["take", "discuss", "skip"]
    summary: str             # 1–2 предложения по сути задачи
    red_flags: list[str]     # например: «нет ТЗ», «срок 1 день»
    estimated_hours: str     # «8–16 ч» (диапазон, не обещание)
    draft_reply: str         # готовый вежливый ответ клиенту

class LeadCard(BaseModel):
    message: RawMessage
    verdict: Verdict
```

SQLite-схема:

```sql
CREATE TABLE leads (
  id            INTEGER PRIMARY KEY,
  chat_id       INTEGER NOT NULL,
  message_id    INTEGER NOT NULL,
  chat_title    TEXT,
  sender_id     INTEGER,
  sender_username TEXT,
  text          TEXT NOT NULL,
  link          TEXT,
  created_at    TEXT NOT NULL,
  status        TEXT NOT NULL,   -- new|filtered_out|evaluated|sent|failed
  difficulty    INTEGER,
  fit           TEXT,
  verdict_json  TEXT,
  draft_reply   TEXT,
  sent_at       TEXT,
  UNIQUE(chat_id, message_id)    -- идемпотентность
);
```

## 4. Конфиг (черновик)

```yaml
telegram:
  session: data/scout.session
  source_chats: ["@freelance_chat", -1001234567890]
  notify_chat_id: -1009876543210
  ignore_forwards: true
  ignore_bots: true

filters:
  whitelist:
    - "нужен сайт"
    - "сделать бота"
    - "написать парсер"
    - "python"
    - "html/css"
  stopwords:
    - "1с"
    - "битрикс"
    - "java"
    - "android"
    - "за отзыв"
  min_length: 40
  max_length: 4000

ai:
  model: "claude-sonnet-4-5"   # модель меняется без правок кода
  max_difficulty: 3            # 4–5 → fit=skip, карточка всё равно уходит
  max_input_chars: 4000
  concurrency: 2
  daily_budget_usd: 3.0

pipeline:
  queue_size: 200
  workers: 2
```

Секреты — только из `.env`, в YAML их нет. `config.py` валидирует всё на старте
и падает с понятной ошибкой, если чего-то не хватает.

## 5. Ключевые решения

**Telethon, не Pyrogram.** Обе библиотеки умеют realtime, но у Telethon более
зрелый API событий, понятные `FloodWaitError` и удобный `get_entity` для ссылок.
Сессия создаётся один раз через `scripts/login.py`.

**Префильтр — обычный Python, без LLM.** Нормализация (`ё→е`, нижний регистр,
схлопывание пробелов) + поиск по границам слов. Для «python» это важно, чтобы не
ловить «pythonic» в вакансиях. Стоп-слова имеют приоритет над белым списком.
Порог: нужно ≥1 совпадение из whitelist (фразы весят больше одиночных слов).

**Structured output через tool use / JSON schema.** Claude обязан вернуть объект
по схеме; `schema.py` валидирует через pydantic. Невалидный ответ = один retry,
потом `status=failed`, остальной пайплайн живёт.

**Очередь и воркеры.** `events.NewMessage` должен возвращаться мгновенно, иначе
Telethon копит апдейты. Хендлер делает только префильтр и `queue.put_nowait`.
Отдельные воркеры ходят в Claude с семафором `concurrency=2`.

**Полуавтомат.** Бот присылает карточку с кнопкой «Скопировать отклик»
(или просто текст в `<code>`), но **никогда не отправляет ответ клиенту сам**.
Это снижает риск бана и ошибок из-за галлюцинаций.

**Ссылка на клиента.** `resolver.py`:
- публичный чат/канал → `https://t.me/<username>/<message_id>`;
- приватный супергруппа → `https://t.me/c/<id без -100>/<message_id>`;
- личка → `tg://openmessage?user_id=<sender_id>` (плюс `@username`, если есть).

**Идемпотентность.** `UNIQUE(chat_id, message_id)` + проверка перед постановкой
в очередь. Дополнительно можно хэшировать текст, чтобы ловить кросс-постинг
одного заказа в разные чаты (P2).

## 6. Промпт (суть)

`config/prompts/system.md`:

```
Ты — технический лид небольшой веб-студии.
Стек, который мы делаем хорошо: Python (FastAPI, aiogram, парсинг),
TypeScript/React/Next.js, HTML/CSS, PostgreSQL, Docker, интеграции API.
Не берём: 1С, Битрикс, Java, Android, нативные мобильные приложения,
задачи «за отзыв» и «бесплатно за кейс».

Оцени задачу по сложности для нашего стека: 1 — просто, 5 — не наш профиль.
Верни ТОЛЬКО JSON по схеме.

Правила для draft_reply:
- язык оригинала, обращение по имени, если известно;
- 3–5 предложений, без воды и без «здравствуйте, меня зовут...»;
- сошлись на 1–2 конкретные детали задачи;
- задай 1–2 уточняющих вопроса;
- диапазон сроков, без финальной цены и без обещаний;
- не вставляй ссылки, не предлагай созвон первым сообщением.
```

Системный промпт кэшируется (`cache_control: ephemeral`), в запрос уходит только
текст сообщения + метаданные чата. Это основная экономия.

## 7. Карточка в закрытом чате

```
🟢 ЛИД · сложность 2/5 · берём
📌 @freelance_chat · 14:32
👤 Иван (@ivan_p) · #12345
💬 Нужен парсер карточек товара с Wildberries, ~5k позиций...
🧠 Суть: типовой парсинг + выгрузка в CSV, наш стек.
⚠️ Риски: нет ТЗ по формату выгрузки.
✍️ Черновик:
Иван, привет! По парсеру Wildberries — делали похожее...
🔗 Открыть сообщение
```

Сообщение отправляется через `aiogram` с `parse_mode=HTML` и экранированием
пользовательского текста (`utils/text.py`), чтобы не ловить ошибки разметки.

## 8. Надёжность и эксплуатация

- **FloodWait / 429 / 5xx:** экспоненциальный backoff с джиттером, лимит попыток.
- **Дневной бюджет:** счётчик расходов в SQLite; при превышении новые лиды
  складываются со статусом `new`, но в LLM не уходят до сброса.
- **Graceful shutdown:** по SIGINT/SIGTERM дожидаемся очереди (таймаут) и закрываем
  Telethon/aiogram/SQLite.
- **Логи:** JSON, у каждого лида `lead_id`, стадии `received → filtered → evaluated → sent`.
- **Метрики (P2):** счётчики «принято/отфильтровано/оценено/отправлено» + `/stats` в боте.
- **Тесты:** фикстуры из реальных сообщений; `scripts/replay.py` прогоняет их
  без Telegram и без реальных вызовов Claude (`--dry-run`).
- **Mock-replay:** `MessageHandler` не зависит от Telethon, поэтому один и тот же
  код работает и с реальным событием, и с `FakeEvent`. `tests/fixtures/messages.json`
  — общий набор сценариев для тестов этапов 1–3.

## 9. Этапы

1. **Скелет:** `pyproject.toml`, `config.py`, `models.py`, логирование, `.env.example`.
2. **Telegram:** `scripts/login.py`, `listener.py`, `resolver.py`; просто логируем сообщения.
3. **Фильтры:** `normalize.py`, `keywords.py`, `pipeline.py` + тесты на фикстурах.
4. **Claude:** `schema.py`, `prompts.py`, `claude.py`; dry-run на фикстурах.
5. **Карточки:** `bot.py`, `processor.py`, сквозной тест в тестовом чате.
6. **Харденинг:** дедуп, ретраи, бюджет, graceful shutdown, `/stats`.

## 10. Юридические и этические заметки

- Читаем только чаты, где аккаунт уже состоит; уважаем правила чатов.
- Не рассылаем автоматически: бот готовит черновик, отправляет человек.
- Храним минимум персональных данных, чистим старые записи по TTL.
- Не публикуем и не перепродаём содержимое чатов.
