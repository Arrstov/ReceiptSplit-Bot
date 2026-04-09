from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from aiogram import Bot, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.proverkacheka_client import lookup_receipt_items
from common.config import get_settings
from common.receipt_qr import format_receipt_qr_message, parse_receipt_qr
from common.telegram_auth import validate_init_data
from backend.qr_decoder import decode_qr_from_image_bytes

BASE_DIR = Path(__file__).resolve().parent.parent
WEBAPP_DIR = BASE_DIR / "webapp"

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    yield
    await app.state.bot.session.close()


app = FastAPI(
    title="ReceiptSplit Backend",
    version="0.1.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=WEBAPP_DIR), name="static")


@app.get("/", include_in_schema=False)
async def serve_webapp() -> FileResponse:
    return FileResponse(WEBAPP_DIR / "index.html")


@app.get("/api/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


async def _extract_user_from_init_data(init_data: str | None) -> dict[str, Any] | None:
    if not init_data:
        return None

    validated_data = validate_init_data(
        init_data,
        settings.bot_token,
        ttl_seconds=settings.init_data_ttl_seconds,
    )
    if not validated_data:
        raise HTTPException(
            status_code=403,
            detail="Не удалось проверить Telegram initData.",
        )

    user = validated_data.get("user")
    if not isinstance(user, dict) or "id" not in user:
        raise HTTPException(
            status_code=403,
            detail="В initData нет корректных данных пользователя.",
        )
    return user


def _build_items_preview(items_lookup: dict[str, Any], *, limit: int = 8) -> str:
    items = items_lookup.get("items") or []
    items_count = items_lookup.get("items_count", 0)
    if not items:
        return (
            "\n\n"
            f"Позиции чека: <b>0</b>\n"
            f"{html.quote(str(items_lookup.get('message', 'Позиции не найдены.')))}"
        )

    lines = [f"\n\nПозиции чека: <b>{items_count}</b>"]
    for index, item in enumerate(items[:limit], start=1):
        name = html.quote(str(item.get("name", "Без названия")))
        quantity = html.quote(str(item.get("quantity") or "1"))
        line_total = html.quote(str(item.get("sum") or "?"))
        price = html.quote(str(item.get("price") or "?"))
        lines.append(
            f"{index}. {name} — {quantity} × {price} ₽ = <b>{line_total} ₽</b>"
        )

    if items_count > limit:
        lines.append(f"... и ещё {items_count - limit} поз.")

    return "\n".join(lines)


@app.post("/api/receipts/process-photo")
async def process_receipt_photo(
    request: Request,
    receipt_photo: UploadFile = File(...),
    init_data: str | None = Form(default=None),
) -> dict[str, Any]:
    if not receipt_photo.content_type or not receipt_photo.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Нужно загрузить изображение чека в формате JPG, PNG или похожем.",
        )

    image_bytes = await receipt_photo.read()
    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail="Файл пустой. Загрузите фотографию чека ещё раз.",
        )
    if len(image_bytes) > 12 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="Файл слишком большой. Для MVP используйте изображение до 12 МБ.",
        )

    qr_payload: str | None = None
    local_qr_error: str | None = None
    try:
        qr_payload = decode_qr_from_image_bytes(image_bytes)
    except RuntimeError as exc:
        local_qr_error = str(exc)

    receipt = parse_receipt_qr(qr_payload) if qr_payload else None
    items_lookup: dict[str, Any] = {
        "status": "skipped",
        "message": "Интеграция с внешним сервисом не настроена.",
        "items": [],
        "items_count": 0,
        "receipt_summary": {},
    }

    if settings.proverkacheka_api_token:
        filename = receipt_photo.filename or "receipt.jpg"
        content_type = receipt_photo.content_type or "application/octet-stream"
        try:
            items_lookup = await lookup_receipt_items(
                api_url=settings.proverkacheka_api_url,
                token=settings.proverkacheka_api_token,
                qrraw=qr_payload,
                image_bytes=image_bytes,
                filename=filename,
                content_type=content_type,
                timeout_seconds=settings.proverkacheka_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to request proverkacheka.com API")
            items_lookup = {
                "status": "error",
                "message": f"Ошибка запроса к сервису проверки чеков: {exc}",
                "items": [],
                "items_count": 0,
                "receipt_summary": {},
            }

    receipt_summary = items_lookup.get("receipt_summary") or {}
    if receipt is None and receipt_summary:
        receipt = {
            "timestamp": receipt_summary.get("date_time"),
            "total_amount": receipt_summary.get("total_sum"),
            "fiscal_drive_number": receipt_summary.get("fiscal_drive_number"),
            "fiscal_document_number": receipt_summary.get("fiscal_document_number"),
            "fiscal_sign": receipt_summary.get("fiscal_sign"),
        }

    if qr_payload is None and items_lookup.get("status") != "success":
        if local_qr_error and not settings.proverkacheka_api_token:
            raise HTTPException(
                status_code=503,
                detail=local_qr_error,
            )
        raise HTTPException(
            status_code=422,
            detail=(
                "Не удалось получить данные чека: QR-код не считан, "
                "а внешний сервис тоже не вернул результат."
            ),
        )

    user = await _extract_user_from_init_data(init_data)

    delivery_status = "skipped"
    if hasattr(receipt, "to_dict"):
        receipt_payload = receipt.to_dict()
        message_text = format_receipt_qr_message(receipt)
    else:
        receipt_payload = receipt or {
            "timestamp": None,
            "total_amount": None,
            "fiscal_drive_number": None,
            "fiscal_document_number": None,
            "fiscal_sign": None,
        }
        timestamp = receipt_payload.get("timestamp") or "Не удалось определить"
        total_amount = receipt_payload.get("total_amount") or "Не удалось определить"
        message_text = (
            "<b>Чек обработан</b>\n\n"
            f"Дата и время: <b>{html.quote(str(timestamp))}</b>\n"
            f"Сумма: <b>{html.quote(str(total_amount))}</b>"
        )

    if items_lookup.get("status") == "success":
        message_text += _build_items_preview(items_lookup)
    else:
        message_text += (
            "\n\n"
            "Позиции автоматически не получены.\n"
            f"Источник: <code>{html.quote(str(items_lookup.get('message')))}</code>"
        )

    if user is not None:
        display_name = user.get("first_name") or user.get("username") or "пользователь"
        username = f"@{user['username']}" if user.get("username") else "без username"
        message_text = (
            "<b>ReceiptSplit: фото чека обработано</b>\n\n"
            f"Пользователь: <b>{html.quote(str(display_name))}</b> ({html.quote(username)})\n\n"
            f"{message_text}"
        )

        try:
            await request.app.state.bot.send_message(
                chat_id=int(user["id"]),
                text=message_text,
            )
            delivery_status = "sent"
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to send message to Telegram user")
            raise HTTPException(
                status_code=502,
                detail="Фото обработано, но backend не смог отправить сообщение в Telegram.",
            ) from exc

    return {
        "status": "ok",
        "message": (
            "Чек обработан. Проверьте чат с ботом."
            if delivery_status == "sent"
            else "Чек обработан. Результат показан только в Mini App, потому что initData не передан."
        ),
        "telegram_delivery": delivery_status,
        "qr_payload": qr_payload,
        "receipt": receipt_payload,
        "items_lookup": items_lookup,
    }
