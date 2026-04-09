from __future__ import annotations

import json
import logging
from urllib.parse import urlparse

from aiogram import Bot, Dispatcher, F, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestUsers,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)

from backend.mvp_store import register_group_member, save_shared_contacts, upsert_profile
from common.config import get_settings

settings = get_settings()
dp = Dispatcher()

CONTACTS_REQUEST_ID = 1001


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


def build_request_users_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Выбрать участников из контактов",
                    request_users=KeyboardButtonRequestUsers(
                        request_id=CONTACTS_REQUEST_ID,
                        max_quantity=20,
                        request_name=True,
                        request_username=True,
                    ),
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def _send_contacts_request_prompt(message: Message) -> None:
    await message.answer(
        "Нажмите кнопку ниже и выберите людей из Telegram-контактов.\n"
        "После этого они появятся в Mini App в списке участников.",
        reply_markup=build_request_users_keyboard(),
    )


@dp.message(CommandStart())
async def handle_start(message: Message) -> None:
    if message.from_user:
        upsert_profile(message.from_user.model_dump())

    start_arg = ""
    if message.text and " " in message.text:
        start_arg = message.text.split(" ", maxsplit=1)[1].strip().lower()

    if start_arg == "contacts":
        await _send_contacts_request_prompt(message)
        return

    keyboard = build_webapp_keyboard()
    text = (
        "<b>ReceiptSplit Bot</b>\n\n"
        "Откройте Mini App кнопкой ниже, чтобы создавать события и делить чеки.\n\n"
        "Для быстрого добавления людей используйте команду <code>/contacts</code>.\n"
        "Для группового сценария добавьте бота в чат и попросите участников отправить <code>/join</code>."
    )

    if keyboard is None:
        text += (
            "\n\n"
            "<b>Mini App пока не подключён.</b>\n"
            "Укажите в файле <code>.env</code> переменную <code>WEBAPP_URL</code> "
            "с публичным HTTPS-адресом, затем перезапустите backend и бота."
        )
        await message.answer(text)
        return

    await message.answer(text, reply_markup=keyboard)


@dp.message(Command("contacts"), F.chat.type == "private")
async def handle_contacts_command(message: Message) -> None:
    if message.from_user:
        upsert_profile(message.from_user.model_dump())
    await _send_contacts_request_prompt(message)


@dp.message(F.users_shared)
async def handle_users_shared(message: Message) -> None:
    if message.from_user is None or message.users_shared is None:
        return

    owner = upsert_profile(message.from_user.model_dump())
    shared_users = []
    for shared_user in message.users_shared.users:
        shared_users.append(
            {
                "user_id": shared_user.user_id,
                "first_name": shared_user.first_name,
                "last_name": shared_user.last_name,
                "username": shared_user.username,
            }
        )

    saved = save_shared_contacts(owner["user_id"], shared_users)
    await message.answer(
        f"Готово, добавлено контактов: <b>{saved}</b>.\n"
        "Вернитесь в Mini App и обновите данные.",
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(Command("join"), F.chat.type.in_({"group", "supergroup"}))
async def handle_join_group(message: Message) -> None:
    if message.from_user is None:
        return

    register_group_member(
        chat_id=message.chat.id,
        chat_title=message.chat.title or "Telegram Group",
        user=message.from_user.model_dump(),
    )
    await message.reply(
        "Супер, добавил вас в список участников этой группы.\n"
        "Теперь организатор сможет импортировать участников в Mini App."
    )


@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def remember_group_member(message: Message) -> None:
    if message.from_user is None or message.from_user.is_bot:
        return

    register_group_member(
        chat_id=message.chat.id,
        chat_title=message.chat.title or "Telegram Group",
        user=message.from_user.model_dump(),
    )


@dp.message(F.web_app_data)
async def handle_web_app_data(message: Message) -> None:
    try:
        payload = json.loads(message.web_app_data.data)
    except json.JSONDecodeError:
        await message.answer("Получил данные из Mini App, но не смог разобрать JSON.")
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
