from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import parse_qsl, urlparse

OPERATION_TYPES = {
    "1": "Приход",
    "2": "Возврат прихода",
    "3": "Расход",
    "4": "Возврат расхода",
}


@dataclass(slots=True)
class ReceiptQrData:
    raw_payload: str
    timestamp: datetime | None
    total_amount: Decimal | None
    fiscal_drive_number: str | None
    fiscal_document_number: str | None
    fiscal_sign: str | None
    operation_type_code: str | None
    operation_type_name: str | None
    fields: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = (
            self.timestamp.isoformat(timespec="minutes") if self.timestamp else None
        )
        data["total_amount"] = (
            f"{self.total_amount:.2f}" if self.total_amount is not None else None
        )
        return data


def _extract_query(raw_payload: str) -> str:
    payload = raw_payload.strip()
    parsed_url = urlparse(payload)
    if parsed_url.scheme in {"http", "https"} and parsed_url.query:
        return parsed_url.query
    return payload.lstrip("?")


def _parse_timestamp(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None

    for pattern in ("%Y%m%dT%H%M", "%Y%m%dT%H%M%S"):
        try:
            return datetime.strptime(raw_value, pattern)
        except ValueError:
            continue
    return None


def _parse_amount(raw_value: str | None) -> Decimal | None:
    if not raw_value:
        return None

    normalized = raw_value.replace(",", ".").strip()
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def parse_receipt_qr(raw_payload: str) -> ReceiptQrData:
    query = _extract_query(raw_payload)
    raw_fields = dict(parse_qsl(query, keep_blank_values=True))
    fields = {key.lower(): value for key, value in raw_fields.items()}

    operation_type_code = fields.get("n")
    return ReceiptQrData(
        raw_payload=raw_payload.strip(),
        timestamp=_parse_timestamp(fields.get("t")),
        total_amount=_parse_amount(fields.get("s")),
        fiscal_drive_number=fields.get("fn"),
        fiscal_document_number=fields.get("i"),
        fiscal_sign=fields.get("fp") or fields.get("fpd"),
        operation_type_code=operation_type_code,
        operation_type_name=OPERATION_TYPES.get(operation_type_code),
        fields=fields,
    )


def format_receipt_qr_message(receipt: ReceiptQrData) -> str:
    timestamp = (
        receipt.timestamp.strftime("%d.%m.%Y %H:%M")
        if receipt.timestamp
        else "Не удалось определить"
    )
    total_amount = (
        f"{receipt.total_amount:.2f} ₽"
        if receipt.total_amount is not None
        else "Не удалось определить"
    )
    operation = receipt.operation_type_name or "Не удалось определить"
    fiscal_drive = receipt.fiscal_drive_number or "Не найден"
    fiscal_document = receipt.fiscal_document_number or "Не найден"
    fiscal_sign = receipt.fiscal_sign or "Не найден"

    return (
        "<b>Чек обработан по QR</b>\n\n"
        f"Дата и время: <b>{timestamp}</b>\n"
        f"Сумма: <b>{total_amount}</b>\n"
        f"Тип операции: <b>{operation}</b>\n"
        f"ФН: <code>{fiscal_drive}</code>\n"
        f"ФД: <code>{fiscal_document}</code>\n"
        f"ФП: <code>{fiscal_sign}</code>\n\n"
        "Позиции пока не извлечены автоматически.\n"
        "Причина: QR на кассовом чеке обычно содержит реквизиты чека, "
        "а для полного состава товаров нужен внешний источник данных "
        "(например, интеграция с ФНС)."
    )

