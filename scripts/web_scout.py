import asyncio
from datetime import datetime
import html
import re
from pathlib import Path
import aiosqlite
import httpx
import structlog

from ai_scout.ai import AIService
from ai_scout.storage.db import Database
from ai_scout.storage.repository import LeadRepository, RawMessage

logger = structlog.get_logger()

# Сюда можно добавлять любые открытые Telegram-каналы (без @ и без ссылки, только имя)
CHANNELS = [
    "SearchEditorr",
]

# Фильтры для отбора заказов (можешь легко менять под себя)
STOP_WORDS = [
    # Непрофильные задачи
    "1с", "битрикс", "bitrix", "менеджер по продажам", "холодные звонки",
    # Анти-резюме (отсекаем чужую саморекламу исполнителей)
    "#резюме", "резюме", "моё портфолио", "мое портфолио", "смотреть портфолио",
    "ищу работу", "ищу заказы", "возьму заказы", "свободен для заказов",
    "владею софтом", "не делаю:", "прайс на услуги", "мои кейсы"
]



def load_env_vars() -> dict[str, str]:
    """Читает ключи из .env напрямую без внешних библиотек."""
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


def parse_telegram_web_html(raw_html: str, channel: str) -> list[dict]:
    """Извлекает посты из публичной веб-ленты Telegram."""
    posts: list[dict] = []
    # Ищем каждый блок сообщения вида data-post="ChannelName/1234"
    blocks = re.split(r'(?=<div class="tgme_widget_message\b)', raw_html)
    for block in blocks:
        post_match = re.search(r'data-post="' + re.escape(channel) + r'/(\d+)"', block, re.IGNORECASE)
        if not post_match:
            continue
        msg_id = int(post_match.group(1))

        text_match = re.search(
            r'<div class="tgme_widget_message_text js-message_text"[^>]*>(.*?)</div>',
            block,
            re.DOTALL,
        )
        if not text_match:
            continue

        raw_text = text_match.group(1)
        clean_text = re.sub(r"<br\s*/?>", "\n", raw_text)
        clean_text = re.sub(r"<[^>]+>", "", clean_text)
        clean_text = html.unescape(clean_text).strip()

        if len(clean_text) < 20:
            continue

        post_link = "".join(["https://", "t.me/", channel, "/", str(msg_id)])
        posts.append(
            {
                "channel": channel,
                "message_id": msg_id,
                "text": clean_text,
                "link": post_link,
            }
        )
    return posts


async def fetch_channel_posts(client: httpx.AsyncClient, channel: str) -> list[dict]:
    """Скачивает открытую веб-ленту канала."""
    url = "".join(["https://", "t.me/s/", channel])
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    }
    try:
        resp = await client.get(url, headers=headers, follow_redirects=True)
        if resp.status_code != 200:
            logger.error("ошибка_загрузки_канала", channel=channel, status=resp.status_code)
            return []
        return parse_telegram_web_html(resp.text, channel)
    except Exception as exc:
        logger.error("сбой_сети_при_чтении_канала", channel=channel, error=str(exc))
        return []


async def send_telegram_lead(client: httpx.AsyncClient, bot_token: str, chat_id: str, post: dict, proposal: str) -> None:
    """Отправляет карточку реального заказа и готовый отклик в Telegram-бот."""
    if not bot_token or not chat_id:
        logger.warn("пропуск_отправки_в_телеграм", reason="Нет токена или CHAT_ID")
        return

    safe_order = html.escape(post["text"][:1200])
    safe_proposal = html.escape(proposal[:2200])

    message_html = (
        f"🔥 <b>Реальный заказ из канала @{post['channel']}!</b>\n"
        f"🔗 <a href=\"{post['link']}\">Открыть оригинальный пост в Telegram</a>\n\n"
        f"📝 <b>Текст заказа:</b>\n{safe_order}\n\n"
        f"✍️ <b>Готовый отклик от ИИ:</b>\n<code>{safe_proposal}</code>"
    )

    api_base = "".join(["https://", "api.", "telegram.org", "/bot", bot_token])
    resp = await client.post(
        api_base + "/sendMessage",
        json={
            "chat_id": chat_id,
            "text": message_html,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
    )
    if resp.status_code == 200:
        logger.info("заказ_отправлен_в_личку", channel=post["channel"], msg_id=post["message_id"])
    else:
        logger.error("ошибка_отправки_в_бота", status=resp.status_code, body=resp.text)


async def run_web_scout() -> None:
    env_vars = load_env_vars()
    db_path = "data/scout.db"
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    class StorageMock:
        pass

    StorageMock.db_path = db_path
    db = Database(StorageMock())

    ai_service = AIService()
    ai_service.api_key = env_vars.get("ANTHROPIC_API_KEY", "")

    bot_token = env_vars.get("TELEGRAM_BOT_TOKEN", "")
    notify_chat_id = env_vars.get("TELEGRAM_NOTIFY_CHAT_ID", "")

    logger.info("старт_разведки_каналов", channels=CHANNELS)

    async with aiosqlite.connect(db_path) as connection:
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

        object.__setattr__(db, "_conn", connection)
        repository = LeadRepository(db)

        async with httpx.AsyncClient(timeout=25.0) as client:
            for channel in CHANNELS:
                posts = await fetch_channel_posts(client, channel)
                logger.info("загружено_постов_из_канала", channel=channel, count=len(posts))

                # Берем последние 10 постов канала, чтобы не заспамить при первом запуске
                recent_posts = posts[-10:]
                channel_numeric_id = abs(hash(channel)) % (10**10)

                for post in recent_posts:
                    raw_msg = RawMessage(
                        chat_id=channel_numeric_id,
                        chat_title=channel,
                        message_id=post["message_id"],
                        text=post["text"],
                        sender_id=0,
                        sender_name=channel,
                        sender_username=channel,
                        date=datetime.now(),
                        link=post["link"],
                    )

                    is_new = await repository.save_raw_message(raw_msg)
                    if not is_new:
                        continue

                    text_lower = post["text"].lower()
                    if any(sw in text_lower for sw in STOP_WORDS):
                        logger.info("отсеяно_стоп_словом", channel=channel, msg_id=post["message_id"])
                        continue

                    if any(aw in text_lower for aw in ALLOWED_WORDS):
                        logger.info("найден_реальный_заказ", channel=channel, msg_id=post["message_id"])
                        print(f"\n🎯 [РЕАЛЬНЫЙ ЗАКАЗ из @{channel} #{post['message_id']}]")
                        proposal = await ai_service.generate_proposal(post["text"])
                        await send_telegram_lead(client, bot_token, notify_chat_id, post, proposal)

    logger.info("разведка_завершена", status="DONE")


if __name__ == "__main__":
    asyncio.run(run_web_scout())
