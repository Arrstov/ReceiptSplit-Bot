from __future__ import annotations

import json
import logging
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from common.config import get_settings

settings = get_settings()
dp = Dispatcher()


def is_valid_webapp_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return False
    if "your-public-https-url" in url:
        return False
    return True


def build_webapp_keyboard() -> InlineKeyboardMarkup | None:
    if not is_valid_webapp_url(settings.normalized_webapp_url):
        return None

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть приложение",
                    web_app=WebAppInfo(url=settings.normalized_webapp_url),
                )
            ]
        ]
    )


@dp.message(CommandStart())
async def handle_start(message: Message) -> None:
    keyboard = build_webapp_keyboard()
    text = (
        "<b>ReceiptSplit Bot</b>\n\n"
        "Это базовый MVP с Telegram Mini App.\n"
        "Нажмите кнопку ниже, чтобы открыть встроенное окно внутри Telegram, "
        "отправить короткие данные и получить ответ обратно в чат."
    )

    if keyboard is None:
        text += (
            "\n\n"
            "<b>Mini App пока не подключён.</b>\n"
            "Укажите в файле <code>.env</code> переменную <code>WEBAPP_URL</code> "
            "с публичным HTTPS адресом, затем перезапустите backend и бота."
        )
        await message.answer(text)
        return

    text += "\n\nВажно: Mini App должен открываться из Telegram и по публичному HTTPS URL."
    await message.answer(text, reply_markup=keyboard)


@dp.message(F.web_app_data)
async def handle_web_app_data(message: Message) -> None:
    try:
        payload = json.loads(message.web_app_data.data)
    except json.JSONDecodeError:
        await message.answer(
            "Получил данные из Mini App, но не смог разобрать JSON."
        )
        return

    receipt_name = payload.get("receipt_name", "Без названия")
    source = payload.get("source", "sendData")
    await message.answer(
        "Получил данные из Mini App.\n"
        f"Название чека: <b>{html.quote(str(receipt_name))}</b>\n"
        f"Источник: <code>{html.quote(str(source))}</code>"
    )


async def main() -> None:
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
