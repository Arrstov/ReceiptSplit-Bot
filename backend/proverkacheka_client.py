from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

def _import_httpx():
    try:
        import httpx  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "Для интеграции с proverkacheka.com не установлена зависимость httpx. "
            "Выполните 'pip install -r requirements.txt' в активированном .venv."
        ) from exc
    return httpx


def _normalize_money(value: Any) -> str | None:
    if value is None or value == "":
        return None

    if isinstance(value, int):
        amount = Decimal(value) / Decimal("100")
        return f"{amount:.2f}"

    if isinstance(value, float):
        return f"{Decimal(str(value)):.2f}"

    if isinstance(value, str):
        normalized = value.strip().replace(",", ".")
        try:
            amount = Decimal(normalized)
        except InvalidOperation:
            return None
        return f"{amount:.2f}"

    return None


def _normalize_quantity(value: Any) -> str | None:
    if value is None or value == "":
        return None

    if isinstance(value, int):
        return str(value)

    if isinstance(value, float):
        normalized = f"{value:.3f}".rstrip("0").rstrip(".")
        return normalized

    if isinstance(value, str):
        normalized = value.strip().replace(",", ".")
        try:
            decimal_value = Decimal(normalized)
        except InvalidOperation:
            return normalized
        return format(decimal_value.normalize(), "f").rstrip("0").rstrip(".") or "0"

    return str(value)


def _find_items_node(payload: Any) -> list[dict[str, Any]] | None:
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list) and all(isinstance(item, dict) for item in items):
            return items
        for value in payload.values():
            result = _find_items_node(value)
            if result:
                return result
    elif isinstance(payload, list):
        for value in payload:
            result = _find_items_node(value)
            if result:
                return result
    return None


def _find_first_dict(payload: Any, keys: tuple[str, ...]) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return None


def _extract_receipt_json(response_payload: dict[str, Any]) -> dict[str, Any] | None:
    data = response_payload.get("data")
    if isinstance(data, dict):
        if isinstance(data.get("json"), dict):
            return data["json"]
        for candidate in ("receipt", "document", "ticket"):
            nested = _find_first_dict(data, (candidate,))
            if nested:
                return nested
        return data

    if isinstance(response_payload.get("json"), dict):
        return response_payload["json"]

    return None


def _extract_receipt_summary(receipt_json: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "seller": receipt_json.get("user") or receipt_json.get("seller"),
        "retail_place": receipt_json.get("retailPlace"),
        "total_sum": _normalize_money(receipt_json.get("totalSum")),
        "date_time": receipt_json.get("dateTime"),
        "fiscal_drive_number": receipt_json.get("fiscalDriveNumber"),
        "fiscal_document_number": receipt_json.get("fiscalDocumentNumber"),
        "fiscal_sign": (
            receipt_json.get("fiscalSign")
            or receipt_json.get("fiscalSignOperator")
        ),
    }
    return summary


def _extract_items(items_payload: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in items_payload:
        name = (
            item.get("name")
            or item.get("productName")
            or item.get("title")
            or "Без названия"
        )
        items.append(
            {
                "name": str(name),
                "quantity": _normalize_quantity(
                    item.get("quantity") or item.get("qty") or item.get("count")
                ),
                "price": _normalize_money(item.get("price")),
                "sum": _normalize_money(
                    item.get("sum") or item.get("amount") or item.get("total")
                ),
            }
        )
    return items


async def lookup_receipt_items(
    *,
    api_url: str,
    token: str,
    qrraw: str | None,
    image_bytes: bytes,
    filename: str,
    content_type: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    httpx = _import_httpx()
    data = {"token": token}
    files = None

    if qrraw:
        data["qrraw"] = qrraw
        request_mode = "qrraw"
    else:
        files = {"qrfile": (filename, image_bytes, content_type)}
        request_mode = "qrfile"

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(api_url, data=data, files=files)

    if response.status_code >= 400:
        return {
            "status": "error",
            "request_mode": request_mode,
            "message": f"Сервис проверки чеков вернул HTTP {response.status_code}.",
            "items": [],
            "items_count": 0,
            "receipt_summary": {},
            "raw_response": response.text[:800],
        }

    try:
        payload = response.json()
    except ValueError:
        return {
            "status": "error",
            "request_mode": request_mode,
            "message": "Сервис проверки чеков вернул не-JSON ответ.",
            "items": [],
            "items_count": 0,
            "receipt_summary": {},
            "raw_response": response.text[:800],
        }

    if payload.get("code") != 1:
        return {
            "status": "error",
            "request_mode": request_mode,
            "message": (
                payload.get("text")
                or payload.get("message")
                or payload.get("error")
                or "Сервис проверки чеков не смог вернуть данные чека."
            ),
            "items": [],
            "items_count": 0,
            "receipt_summary": {},
            "raw_response": payload,
        }

    receipt_json = _extract_receipt_json(payload) or {}
    raw_items = _find_items_node(receipt_json) or []
    items = _extract_items(raw_items)
    receipt_summary = _extract_receipt_summary(receipt_json)

    return {
        "status": "success",
        "request_mode": request_mode,
        "message": (
            f"Сервис проверки чеков вернул {len(items)} поз."
            if items
            else "Чек найден, но позиции в ответе не обнаружены."
        ),
        "items": items,
        "items_count": len(items),
        "receipt_summary": receipt_summary,
        "raw_response": payload,
    }
