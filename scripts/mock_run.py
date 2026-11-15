import asyncio
from datetime import datetime
import structlog
import aiosqlite
import httpx
import os
from pathlib import Path
from ai_scout.storage.repository import LeadRepository, LeadStatus, RawMessage
from ai_scout.storage.db import Database
from ai_scout.ai import AIService

logger = structlog.get_logger()

MOCK_MESSAGES = [
    {
        "chat_id": -100123456789,
        "chat_name": "Фриланс Биржа ИТ",
        "message_id": 5001,
        "text": "Нужен программист! Требуется написать асинхронный парсер на Python для сбора данных с сайтов. Оплата по договору.",
        "sender_id": 99901,
        "sender_name": "Алексей Иванов"
    },
    {
        "chat_id": -100987654321,
        "chat_name": "Shorts/Reels Монтаж Вакансии",
        "message_id": 6002,
        "text": "Ищу человека на постоянную основу, нужно монтировать ролики Shorts/Reels, накладывать субтитры и вырезать паузы. Пишите в ЛС.",
        "sender_id": 99902,
        "sender_name": "Мария Смирнова"
    },
    {
        "chat_id": -100123456789,
        "chat_name": "Фриланс Биржа ИТ",
        "message_id": 5003,
        "text": "Срочно ищу специалиста по 1С-Битрикс, нужно перенести интернет-магазин и настроить бухгалтерию. Бюджет 500 руб.",
        "sender_id": 99903,
        "sender_name": "Заказчик 1С"
    }
]


def load_env_vars() -> dict[str, str]:
    """Безопасно читает все ключи из .env напрямую без внешних зависимостей."""
    env_map: dict[str, str] = {}
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            env_map[key.strip()] = val.strip().strip('"').strip("'")
    return env_map


async def resolve_chat_id(bot_token: str, saved_chat_id: str) -> str:
    """Берет CHAT_ID из .env или автоматически находит его по последнему /start у бота."""
    if saved_chat_id:
        return saved_chat_id
    if not bot_token:
        return ""
    api_base = "".join(["https://", "api.", "telegram.org", "/bot", bot_token])
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(api_base + "/getUpdates")
        data = resp.json()
        updates = data.get("result", [])
        if updates:
            last_msg = updates[-1].get("message") or updates[-1].get("edited_message") or {}
            chat_id = str(last_msg.get("chat", {}).get("id", ""))
            if chat_id:
                print(f"\n🔑 Нашли твой TELEGRAM_NOTIFY_CHAT_ID: {chat_id} (впиши его в 11-ю строку .env!)")
                return chat_id
    return ""


async def send_telegram_lead(bot_token: str, chat_id: str, msg: dict, proposal: str) -> None:
    """Отправляет карточку заказа и готовый отклик в личку через Telegram Bot API."""
    if not bot_token or not chat_id:
        logger.warn("пропуск_отправки_в_телеграм", reason="Не заполнен TELEGRAM_BOT_TOKEN или CHAT_ID")
        return

    text = (
        f"🎯 <b>Новый подходящий заказ!</b>\n"
        f"📌 <b>Чат:</b> {msg['chat_name']}\n"
        f"👤 <b>Заказчик:</b> {msg['sender_name']}\n\n"
        f"📝 <b>Суть заказа:</b>\n{msg['text']}\n\n"
        f"✍️ <b>Готовый отклик от ИИ:</b>\n<code>{proposal}</code>"
    )

    api_base = "".join(["https://", "api.", "telegram.org", "/bot", bot_token])
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            api_base + "/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            },
        )
        if resp.status_code == 200:
            logger.info("уведомление_отправлено_в_телеграм", msg_id=msg["message_id"])
        else:
            logger.error("ошибка_отправки_в_телеграм", status=resp.status_code, body=resp.text)


async def simulate_pipeline():
    env_vars = load_env_vars()
    clean_path = "data/scout.db"
    Path(clean_path).parent.mkdir(parents=True, exist_ok=True)

    class StorageMock:
        db_path = clean_path

    db = Database(StorageMock())
    ai_service = AIService()
    ai_service.api_key = env_vars.get("ANTHROPIC_API_KEY", "")

    bot_token = env_vars.get("TELEGRAM_BOT_TOKEN", "")
    notify_chat_id = await resolve_chat_id(bot_token, env_vars.get("TELEGRAM_NOTIFY_CHAT_ID", ""))

    logger.info("запуск_автономной_ИИ_симуляции", status="START", total_messages=len(MOCK_MESSAGES))

    async with aiosqlite.connect(clean_path) as connection:
        connection.row_factory = aiosqlite.Row

        await connection.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                chat_id INTEGER,
                chat_title TEXT,
                message_id INTEGER,
                text TEXT,
                sender_id INTEGER,
                sender_name TEXT,
                sender_username TEXT,
                status TEXT,
                message_date TEXT,
                received_at TEXT,
                link TEXT,
                PRIMARY KEY (chat_id, message_id)
            )
        """)
        await connection.commit()

        object.__setattr__(db, '_conn', connection)
        repository = LeadRepository(db)

        for msg in MOCK_MESSAGES:
            logger.info("получено_новое_сообщение", chat=msg["chat_name"], msg_id=msg["message_id"])

            raw_msg_obj = RawMessage(
                chat_id=msg["chat_id"],
                chat_title=msg["chat_name"],
                message_id=msg["message_id"],
                text=msg["text"],
                sender_id=msg["sender_id"],
                sender_name=msg["sender_name"],
                sender_username=f"user_{msg['sender_id']}",
                date=datetime.now(),
                link=f"https://t.me{str(msg['chat_id'])[4:]}/{msg['message_id']}"
            )

            is_inserted = await repository.save_raw_message(raw_msg_obj)

            if not is_inserted:
                logger.warn("ОБНАРУЖЕН_ДУБЛИКАТ_ИГНОРИРУЕМ", chat=msg["chat_name"], msg_id=msg["message_id"])
                continue

            logger.info("заказ_успешно_сохранен_в_sqlite", msg_id=msg["message_id"])

            text_lower = msg["text"].lower()
            stop_words = ['1с', 'битрикс', 'bitrix']
            if any(word in text_lower for word in stop_words):
                logger.error("ЗАКАЗ_ОТКЛОНЕН_СТОП_СЛОВОМ", msg_id=msg["message_id"], reason="Обнаружено ключевое слово 1С/Битрикс")
                continue

            allowed_words = ['python', 'парсер', 'монтировать', 'shorts', 'reels', 'субтитры']
            if any(word in text_lower for word in allowed_words):
                logger.info("ЗАКАЗ_ПОДХОДИТ_ОТПРАВЛЯЕМ_В_НЕЙРОСЕТЬ", msg_id=msg["message_id"])

                print(f"\n🤖 [ИИ ДУМАЕТ НАД ЗАКАЗОМ №{msg['message_id']}...]")
                ai_proposal = await ai_service.generate_proposal(msg["text"])
                print(f"✍️ [СФОРМИРОВАННЫЙ ОТКЛИК]:\n{ai_proposal}\n" + "-" * 50)

                await send_telegram_lead(bot_token, notify_chat_id, msg, ai_proposal)
            else:
                logger.info("заказ_пропущен_нет_триггеров", msg_id=msg["message_id"])

    logger.info("симуляция_завершена", status="DONE")


if __name__ == "__main__":
    asyncio.run(simulate_pipeline())
