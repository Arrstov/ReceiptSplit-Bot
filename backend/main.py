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
from pydantic import BaseModel, Field

from backend.mvp_store import (
    add_manual_item_to_event,
    add_receipt_to_event,
    calculate_event,
    create_event,
    get_dashboard,
    get_event_for_user,
    get_profile_stats,
    init_db,
    list_contacts_for_user,
    list_events_for_user,
    list_group_participants_for_user,
    list_groups_for_user,
    list_recent_receipts_for_user,
    set_item_assignment,
    toggle_my_item_assignment,
    update_event,
    update_profile_name,
    upsert_profile,
)
from backend.proverkacheka_client import lookup_receipt_items
from backend.qr_decoder import decode_qr_from_image_bytes
from common.config import get_settings
from common.receipt_qr import format_receipt_qr_message, parse_receipt_qr
from common.telegram_auth import validate_init_data

BASE_DIR = Path(__file__).resolve().parent.parent
WEBAPP_DIR = BASE_DIR / "webapp"

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
logger = logging.getLogger(__name__)


class ParticipantInput(BaseModel):
    user_id: int | None = None
    display_name: str | None = None
    username: str | None = None
    phone: str | None = None


class CreateEventInput(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    event_date: str | None = None
    participants: list[ParticipantInput] = Field(default_factory=list)


class AssignMemberInput(BaseModel):
    member_id: int
    assigned: bool


class ManualItemInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    amount: str
    receipt_id: int | None = None


class UpdateProfileNameInput(BaseModel):
    custom_name: str | None = Field(default=None, max_length=80)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        me = await app.state.bot.get_me()
        app.state.bot_username = me.username
    except Exception:  # noqa: BLE001
        logger.exception("Failed to fetch bot username")
        app.state.bot_username = None
    yield
    await app.state.bot.session.close()


app = FastAPI(
    title="ReceiptSplit Backend",
    version="0.2.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=WEBAPP_DIR), name="static")


@app.get("/", include_in_schema=False)
async def serve_webapp() -> FileResponse:
    return FileResponse(WEBAPP_DIR / "index.html")


@app.get("/api/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


def _default_local_user() -> dict[str, Any]:
    return {
        "id": 900_000_001,
        "username": "local_user",
        "first_name": "Локальный",
        "last_name": "пользователь",
    }


async def _extract_user_from_init_data(
    init_data: str | None,
    *,
    allow_local_fallback: bool,
) -> dict[str, Any]:
    if not init_data:
        if allow_local_fallback:
            return _default_local_user()
        raise HTTPException(status_code=401, detail="initData не передан.")

    validated_data = validate_init_data(
        init_data,
        settings.bot_token,
        ttl_seconds=settings.init_data_ttl_seconds,
    )
    if not validated_data:
        if allow_local_fallback:
            logger.warning("Invalid initData, fallback to local user.")
            return _default_local_user()
        raise HTTPException(status_code=403, detail="Не удалось проверить Telegram initData.")

    user = validated_data.get("user")
    if not isinstance(user, dict) or "id" not in user:
        if allow_local_fallback:
            return _default_local_user()
        raise HTTPException(status_code=403, detail="В initData нет корректных данных пользователя.")

    return user


async def _get_actor(
    request: Request,
    *,
    init_data: str | None = None,
    allow_local_fallback: bool = True,
) -> dict[str, Any]:
    raw_init_data = init_data or request.headers.get("X-Telegram-Init-Data")
    user = await _extract_user_from_init_data(
        raw_init_data,
        allow_local_fallback=allow_local_fallback,
    )
    return upsert_profile(user)


def _build_contacts_request_link(request: Request) -> tuple[str | None, str | None]:
    bot_username = getattr(request.app.state, "bot_username", None)
    if not bot_username:
        return None, None
    https_link = f"https://t.me/{bot_username}?start=contacts"
    tg_link = f"tg://resolve?domain={bot_username}&start=contacts"
    return https_link, tg_link


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
        lines.append(f"{index}. {name} — {quantity} × {price} ₽ = <b>{line_total} ₽</b>")

    if items_count > limit:
        lines.append(f"... и ещё {items_count - limit} поз.")

    return "\n".join(lines)


async def _extract_receipt_data(
    *,
    image_bytes: bytes,
    filename: str,
    content_type: str,
) -> dict[str, Any]:
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
            raise HTTPException(status_code=503, detail=local_qr_error)
        raise HTTPException(
            status_code=422,
            detail=(
                "Не удалось получить данные чека: QR-код не считан, "
                "а внешний сервис тоже не вернул результат."
            ),
        )

    if hasattr(receipt, "to_dict"):
        receipt_payload = receipt.to_dict()
    else:
        receipt_payload = receipt or {
            "timestamp": None,
            "total_amount": None,
            "fiscal_drive_number": None,
            "fiscal_document_number": None,
            "fiscal_sign": None,
        }

    if not items_lookup.get("items"):
        fallback_total = receipt_payload.get("total_amount") or "0"
        items_lookup["items"] = [
            {
                "name": "Общая сумма чека",
                "quantity": "1",
                "price": str(fallback_total),
                "sum": str(fallback_total),
            }
        ]
        items_lookup["items_count"] = 1

    return {
        "qr_payload": qr_payload,
        "receipt": receipt_payload,
        "items_lookup": items_lookup,
    }


def _guess_store_name(items_lookup: dict[str, Any], receipt_payload: dict[str, Any]) -> str:
    summary = items_lookup.get("receipt_summary") or {}
    return (
        summary.get("seller")
        or summary.get("retail_place")
        or receipt_payload.get("seller")
        or "Чек без названия"
    )


@app.get("/api/me")
async def get_me(request: Request) -> dict[str, Any]:
    actor = await _get_actor(request)
    stats = get_profile_stats(actor["user_id"])
    return {
        "profile": actor,
        "stats": stats,
    }


@app.post("/api/me/name")
async def set_my_name(request: Request, payload: UpdateProfileNameInput) -> dict[str, Any]:
    actor = await _get_actor(request)
    try:
        profile = update_profile_name(
            user_id=actor["user_id"],
            custom_name=payload.custom_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "status": "ok",
        "profile": profile,
        "stats": get_profile_stats(actor["user_id"]),
    }


@app.get("/api/contacts")
async def get_contacts(request: Request) -> dict[str, Any]:
    actor = await _get_actor(request)
    contacts = list_contacts_for_user(actor["user_id"], limit=40)
    request_contacts_link, request_contacts_tg_link = _build_contacts_request_link(request)
    return {
        "contacts": contacts,
        "request_contacts_link": request_contacts_link,
        "request_contacts_tg_link": request_contacts_tg_link,
        "request_contacts_command": "/contacts",
    }


@app.get("/api/groups")
async def get_groups(request: Request) -> dict[str, Any]:
    actor = await _get_actor(request)
    groups = list_groups_for_user(actor["user_id"], limit=30)
    return {"groups": groups}


@app.get("/api/groups/{chat_id}/participants")
async def get_group_participants(request: Request, chat_id: int) -> dict[str, Any]:
    actor = await _get_actor(request)
    try:
        participants = list_group_participants_for_user(
            user_id=actor["user_id"],
            chat_id=chat_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    return {"participants": participants}


@app.get("/api/dashboard")
async def dashboard(request: Request) -> dict[str, Any]:
    actor = await _get_actor(request)
    return {
        "dashboard": get_dashboard(actor["user_id"]),
        "stats": get_profile_stats(actor["user_id"]),
    }


@app.get("/api/receipts/recent")
async def recent_receipts(request: Request, limit: int = 30) -> dict[str, Any]:
    actor = await _get_actor(request)
    safe_limit = max(1, min(limit, 200))
    return {
        "receipts": list_recent_receipts_for_user(actor["user_id"], limit=safe_limit),
    }


@app.get("/api/events")
async def list_events(request: Request) -> dict[str, Any]:
    actor = await _get_actor(request)
    return {"events": list_events_for_user(actor["user_id"]) }


@app.post("/api/events")
async def create_event_route(request: Request, payload: CreateEventInput) -> dict[str, Any]:
    actor = await _get_actor(request)
    title = payload.title.strip()
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="Название события слишком короткое.")

    participants_payload = [participant.model_dump() for participant in payload.participants]
    event = create_event(
        owner_user_id=actor["user_id"],
        title=title,
        event_date=payload.event_date,
        participants=participants_payload,
    )
    return {
        "status": "ok",
        "event": event,
    }


@app.put("/api/events/{event_id}")
async def update_event_route(
    request: Request,
    event_id: int,
    payload: CreateEventInput,
) -> dict[str, Any]:
    actor = await _get_actor(request)
    title = payload.title.strip()
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="Название события слишком короткое.")

    participants_payload = [participant.model_dump() for participant in payload.participants]
    try:
        event = update_event(
            event_id=event_id,
            editor_user_id=actor["user_id"],
            title=title,
            event_date=payload.event_date,
            participants=participants_payload,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "status": "ok",
        "event": event,
    }


@app.get("/api/events/{event_id}")
async def event_detail(request: Request, event_id: int) -> dict[str, Any]:
    actor = await _get_actor(request)
    event = get_event_for_user(event_id=event_id, user_id=actor["user_id"])
    if event is None:
        raise HTTPException(status_code=404, detail="Событие не найдено.")

    return event


@app.post("/api/events/{event_id}/receipts/upload")
async def upload_receipt_to_event(
    request: Request,
    event_id: int,
    receipt_photo: UploadFile = File(...),
    init_data: str | None = Form(default=None),
) -> dict[str, Any]:
    actor = await _get_actor(request, init_data=init_data)

    if not receipt_photo.content_type or not receipt_photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Нужно загрузить изображение чека.")

    image_bytes = await receipt_photo.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Файл пустой.")
    if len(image_bytes) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл слишком большой. Максимум 12 МБ.")

    extracted = await _extract_receipt_data(
        image_bytes=image_bytes,
        filename=receipt_photo.filename or "receipt.jpg",
        content_type=receipt_photo.content_type,
    )
    receipt_payload = extracted["receipt"]
    items_lookup = extracted["items_lookup"]

    store_name = _guess_store_name(items_lookup, receipt_payload)

    try:
        save_result = add_receipt_to_event(
            event_id=event_id,
            user_id=actor["user_id"],
            store_name=store_name,
            total_amount=receipt_payload.get("total_amount"),
            receipt_timestamp=receipt_payload.get("timestamp"),
            raw_qr=extracted.get("qr_payload"),
            items=items_lookup.get("items") or [],
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    event = get_event_for_user(event_id=event_id, user_id=actor["user_id"])
    if event is None:
        raise HTTPException(status_code=404, detail="Событие не найдено после загрузки чека.")

    return {
        "status": "ok",
        "message": "Чек добавлен в событие.",
        "saved": save_result,
        "event": event,
    }


@app.post("/api/events/{event_id}/items/manual")
async def add_manual_item(
    request: Request,
    event_id: int,
    payload: ManualItemInput,
) -> dict[str, Any]:
    actor = await _get_actor(request)
    try:
        saved = add_manual_item_to_event(
            event_id=event_id,
            user_id=actor["user_id"],
            name=payload.name,
            amount=payload.amount,
            receipt_id=payload.receipt_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    event = get_event_for_user(event_id=event_id, user_id=actor["user_id"])
    if event is None:
        raise HTTPException(status_code=404, detail="Событие не найдено.")

    return {
        "status": "ok",
        "saved": saved,
        "event": event,
    }


@app.post("/api/events/{event_id}/items/{item_id}/toggle-mine")
async def toggle_mine_item(request: Request, event_id: int, item_id: int) -> dict[str, Any]:
    actor = await _get_actor(request)
    try:
        assigned = toggle_my_item_assignment(
            event_id=event_id,
            item_id=item_id,
            user_id=actor["user_id"],
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    event = get_event_for_user(event_id=event_id, user_id=actor["user_id"])
    if event is None:
        raise HTTPException(status_code=404, detail="Событие не найдено.")

    return {
        "status": "ok",
        "assigned": assigned,
        "event": event,
    }


@app.post("/api/events/{event_id}/items/{item_id}/assign")
async def assign_item(
    request: Request,
    event_id: int,
    item_id: int,
    payload: AssignMemberInput,
) -> dict[str, Any]:
    actor = await _get_actor(request)
    try:
        assigned = set_item_assignment(
            event_id=event_id,
            item_id=item_id,
            member_id=payload.member_id,
            user_id=actor["user_id"],
            assigned=payload.assigned,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    event = get_event_for_user(event_id=event_id, user_id=actor["user_id"])
    if event is None:
        raise HTTPException(status_code=404, detail="Событие не найдено.")

    return {
        "status": "ok",
        "assigned": assigned,
        "event": event,
    }


@app.post("/api/events/{event_id}/calculate")
async def calculate_route(request: Request, event_id: int) -> dict[str, Any]:
    actor = await _get_actor(request)
    try:
        result = calculate_event(event_id=event_id, user_id=actor["user_id"])
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "status": "ok",
        "result": result,
    }


@app.post("/api/receipts/process-photo")
async def process_receipt_photo(
    request: Request,
    receipt_photo: UploadFile = File(...),
    init_data: str | None = Form(default=None),
) -> dict[str, Any]:
    if not receipt_photo.content_type or not receipt_photo.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Нужно загрузить изображение чека.")

    image_bytes = await receipt_photo.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Файл пустой.")
    if len(image_bytes) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Файл слишком большой. Используйте изображение до 12 МБ.")

    extracted = await _extract_receipt_data(
        image_bytes=image_bytes,
        filename=receipt_photo.filename or "receipt.jpg",
        content_type=receipt_photo.content_type,
    )

    actor = await _get_actor(request, init_data=init_data, allow_local_fallback=True)
    message_text = ""
    receipt_payload = extracted["receipt"]
    if extracted.get("qr_payload"):
        try:
            parsed = parse_receipt_qr(extracted["qr_payload"])
            message_text = format_receipt_qr_message(parsed)
        except Exception:  # noqa: BLE001
            message_text = "<b>Чек обработан</b>"
    if not message_text:
        timestamp = receipt_payload.get("timestamp") or "Не удалось определить"
        total_amount = receipt_payload.get("total_amount") or "Не удалось определить"
        message_text = (
            "<b>Чек обработан</b>\n\n"
            f"Дата и время: <b>{html.quote(str(timestamp))}</b>\n"
            f"Сумма: <b>{html.quote(str(total_amount))}</b>"
        )

    message_text += _build_items_preview(extracted["items_lookup"])

    delivery_status = "skipped"
    if actor and actor.get("user_id") and int(actor["user_id"]) != 900_000_001:
        try:
            await request.app.state.bot.send_message(
                chat_id=int(actor["user_id"]),
                text=(
                    "<b>ReceiptSplit: фото чека обработано</b>\n\n"
                    f"Пользователь: <b>{html.quote(str(actor.get('display_name', 'unknown')))}</b>\n\n"
                    f"{message_text}"
                ),
            )
            delivery_status = "sent"
        except Exception:  # noqa: BLE001
            logger.exception("Failed to send message to Telegram user")
            delivery_status = "error"

    return {
        "status": "ok",
        "message": "Чек обработан.",
        "telegram_delivery": delivery_status,
        "qr_payload": extracted.get("qr_payload"),
        "receipt": extracted["receipt"],
        "items_lookup": extracted["items_lookup"],
    }
