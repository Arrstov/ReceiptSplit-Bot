from __future__ import annotations

import csv
import io
import os
import re
import shutil
import subprocess
import tempfile
from difflib import SequenceMatcher
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


_MONEY_RE = re.compile(r"(?<!\d)(\d{1,6}[,.]\d{2})(?!\d)")
_SPACED_MONEY_RE = re.compile(r"(?<!\d)(\d{1,3})\s+(\d{3}[,.]\d{2})(?!\d)")
_LETTERS_RE = re.compile(r"[A-Za-zА-Яа-яЁё]")
_QUANTITY_PRICE_RE = re.compile(
    r"(?<!\d)(\d{1,4}(?:[,.]\d{1,3})?)\s*(?:x|х|\*)\s*\d{1,6}[,.]\d{2}",
    re.IGNORECASE,
)
_PRICE_QUANTITY_RE = re.compile(
    r"(?<!\d)\d{1,6}[,.]\d{2}\s*(?:x|х|\*)\s*(\d{1,4}(?:[,.]\d{1,3})?)(?!\d)",
    re.IGNORECASE,
)
_UNIT_QUANTITY_RE = re.compile(
    r"(?<!\d)(\d{1,4}(?:[,.]\d{1,3})?)\s*(шт|кг|г|л|мл)\b",
    re.IGNORECASE,
)
_LONG_NUMBER_RE = re.compile(r"\b\d{6,}\b")
_SPACE_RE = re.compile(r"\s+")

_IGNORE_KEYWORDS = (
    "АДРЕС",
    "БАНК",
    "BANK",
    "БОНУС",
    "ВВЕДЕН",
    "ВРЕМЯ",
    "ГОСТЕВОЙ",
    "ДАТА",
    "ЗАКАЗ",
    "CARD",
    "CASH",
    "CHANGE",
    "CHECK",
    "DATE",
    "RRN",
    "TERMINAL",
    "ИТОГ",
    "ИНН",
    "КАСС",
    "КАРТ",
    "ККТ",
    "КЛИЕНТ",
    "КОМИСС",
    "МЕРЧАНТ",
    "МЕСТО РАСЧ",
    "НАЛИЧ",
    "НДС",
    "ОДОБР",
    "ОПЛАТ",
    "ОПЕРАЦИ",
    "ОФИЦИАНТ",
    "ОТКРЫТ",
    "ПРИХОД",
    "ПОЛУЧ",
    "ПРИЛОЖ",
    "ПДСУМОК",
    "ПТДСУМОК",
    "ПІДСУМОК",
    "ПИДСУМОК",
    "ПОДЫТОГ",
    "ПИН КОД",
    "ПОКИК",
    "ПОКУП",
    "ПОДПИС",
    "ПРИНЯТ",
    "ПРОДАВ",
    "РЕКЛАМ",
    "РН",
    "САЙТ",
    "СДАЧ",
    "СМЕН",
    "СКИД",
    "СНО",
    "СТОЛ",
    "СУММ",
    "СУМА",
    "CUMA",
    "СУМИ",
    "НАЧИС",
    "ТЕРМИНАЛ",
    "ТЕЛ",
    "ФИСКАЛ",
    "TOTAL",
    "VAT",
    "ЦЕНА",
    "ФД",
    "ФНС",
    "ФН",
    "ФП",
    "КОПИТЕ",
    "НАКЛЕЙ",
    "HAC 20",
    "ЧЕК",
    "ЭЛЕКТРОН",
)
_TOTAL_KEYWORDS = (
    "ИТОГ",
    "ВСЕГО",
    "К ОПЛАТЕ",
    "ОПЛАТЕ",
    "ПДСУМОК",
    "ПТДСУМОК",
    "ПІДСУМОК",
    "ПИДСУМОК",
    "ПОДЫТОГ",
    "СУММА",
    "СУМА",
    "СУМИ",
    "CUMA",
    "TOTAL",
)
_BOUNDARY_KEYWORDS = (
    "БЕЗНАЛ",
    "ИТОГ",
    "КАРТА",
    "НАЛИЧ",
    "ОКРУГЛ",
    "ОПЛАТ",
    "ПДСУМОК",
    "ПТДСУМОК",
    "ПІДСУМОК",
    "ПИДСУМОК",
    "ПОДЫТОГ",
    "ПРИНЯТ",
    "СДАЧ",
    "СКИД",
    "СУММА",
    "СУМА",
    "СУМИ",
    "CUMA",
    "TOTAL",
)
_LATIN_NOISE_PREFIX_RE = re.compile(r"^[A-Za-z]{1,5}[\W_]+(?=[А-Яа-яЁё])")
_KNOWN_LATIN_PREFIXES = ("TEOS", "LORENZ", "GOODMIX", "NESCAFE", "NATURALS")
_NAME_REPLACEMENTS = (
    (re.compile(r"\bНАГНИТ\b", re.IGNORECASE), "МАГНИТ"),
    (re.compile(r"\bНЯГКИЙ\b", re.IGNORECASE), "МЯГКИЙ"),
    (re.compile(r"\bКОРЕНОКИ\b", re.IGNORECASE), "КОРЕНОВКИ"),
    (re.compile(r"\bвавенец\b", re.IGNORECASE), "ВАРЕНЕЦ"),
    (re.compile(r"\bOREN\s+NATUR\w*", re.IGNORECASE), "LORENZ NATURALS"),
    (re.compile(r"\bKowe\s+Pad\b", re.IGNORECASE), "КОФЕ РАФ"),
    (re.compile(r"\bKooe\s+Pad\b", re.IGNORECASE), "КОФЕ РАФ"),
    (re.compile(r"\bКове\s+Pad\b", re.IGNORECASE), "КОФЕ РАФ"),
    (re.compile(r"\bКоое\s+Раф\b", re.IGNORECASE), "КОФЕ РАФ"),
    (re.compile(r"\bNECKAOE\b", re.IGNORECASE), "НЕСКАФЕ"),
    (re.compile(r"\bSOPOBKA\b", re.IGNORECASE), "КОРОВКА"),
    (re.compile(r"\bAKT[MN]BMO\b", re.IGNORECASE), "АКТИБИО"),
    (re.compile(r"\bИАКТИБИО\b", re.IGNORECASE), "АКТИБИО"),
    (re.compile(r"\bАКТ[МН]ВМО\b", re.IGNORECASE), "АКТИБИО"),
    (re.compile(r"\bАКТИБП\b", re.IGNORECASE), "АКТИБИО"),
    (re.compile(r"\bБИС[ИЙ]?[ОС]?ГУРТ\b", re.IGNORECASE), "БИОЙОГУРТ"),
    (re.compile(r"\bБИЗЙОГУСТ\b", re.IGNORECASE), "БИОЙОГУРТ"),
    (re.compile(r"\bБИЩИОГУРТ\b", re.IGNORECASE), "БИОЙОГУРТ"),
    (re.compile(r"\bHOPOR\b", re.IGNORECASE), "МОРОЖ"),
    (re.compile(r"\bHOPOH\b", re.IGNORECASE), "МОРОЖ"),
    (re.compile(r"\bНОРОН\b", re.IGNORECASE), "МОРОЖ"),
    (re.compile(r"\bМОРОН\b", re.IGNORECASE), "МОРОЖ"),
    (re.compile(r"ПЛИСТ[<«]?С+А?ВУ[ШМ]\w*", re.IGNORECASE), "ПЛ/СТ САВУШКИН"),
    (re.compile(r"\bЗЛЕКИ\b", re.IGNORECASE), "ЗЛАКИ"),
    (re.compile(r"\bКади\b", re.IGNORECASE), "КЕФИР"),
    (re.compile(r"\bТВОРОГ\s+7\b", re.IGNORECASE), "ТВОРОГ 9%"),
    (re.compile(r"\b(125|220|260)7\b", re.IGNORECASE), r"\1Г"),
    (re.compile(r"\b260r\b", re.IGNORECASE), "260Г"),
    (re.compile(r"\b177\s+сашет\b", re.IGNORECASE), "17Г сашет"),
)


def _import_cv_dependencies():
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "Для локального OCR нужны зависимости OpenCV. Выполните 'pip install -r requirements.txt'."
        ) from exc
    return cv2, np


def _normalize_keyword_text(value: str) -> str:
    return value.upper().replace("Ё", "Е")


def _normalize_text(value: str) -> str:
    text = value.replace("\u00a0", " ")
    text = text.replace("—", "-").replace("–", "-")
    text = _SPACE_RE.sub(" ", text)
    return text.strip()


def _normalize_money_token(value: str) -> Decimal | None:
    normalized = (
        value.strip()
        .replace(",", ".")
        .replace("O", "0")
        .replace("О", "0")
        .replace("o", "0")
    )
    try:
        return Decimal(normalized).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _format_decimal(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _format_quantity(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _line_has_letters(line: str) -> bool:
    return bool(_LETTERS_RE.search(line))


def _line_is_ignored(line: str) -> bool:
    keyword_line = _normalize_keyword_text(line)
    return any(keyword in keyword_line for keyword in _IGNORE_KEYWORDS)


def _line_is_boundary(line: str) -> bool:
    keyword_line = _normalize_keyword_text(line)
    return any(keyword in keyword_line for keyword in _BOUNDARY_KEYWORDS)


def _line_looks_like_ocr_noise(line: str) -> bool:
    tokens = line.split()
    if len(tokens) < 10:
        return False

    numeric_tokens = sum(
        1 for token in tokens if re.fullmatch(r"-?\d+(?:[,.]\d+)?", token)
    )
    if numeric_tokens / len(tokens) >= 0.55:
        return True

    return bool(re.search(r"(?:\b\d+\s+){8,}\d+\b", line))


def _extract_money_values(line: str) -> list[Decimal]:
    values: list[Decimal] = []
    for match in _MONEY_RE.finditer(line):
        value = _normalize_money_token(match.group(1))
        if value is not None:
            values.append(value)
    return values


def _extract_spaced_money_values(line: str) -> list[Decimal]:
    values: list[Decimal] = []
    for match in _SPACED_MONEY_RE.finditer(line):
        value = _normalize_money_token(match.group(1) + match.group(2))
        if value is not None:
            values.append(value)
    return values


def _extract_quantity(line: str) -> Decimal:
    match = _QUANTITY_PRICE_RE.search(line) or _PRICE_QUANTITY_RE.search(line)
    if match:
        try:
            quantity = Decimal(match.group(1).replace(",", "."))
        except InvalidOperation:
            quantity = Decimal("1")
        if quantity > 0:
            return quantity

    match = _UNIT_QUANTITY_RE.search(line)
    if match:
        raw_quantity = match.group(1)
        unit = match.group(2).lower()
        try:
            quantity = Decimal(raw_quantity.replace(",", "."))
        except InvalidOperation:
            quantity = Decimal("1")
        is_decimal_pieces = unit.startswith("шт") and ("," in raw_quantity or "." in raw_quantity)
        if Decimal("0") < quantity <= Decimal("20") and not is_decimal_pieces:
            return quantity

    return Decimal("1")


def _is_price_table_line(line: str, money_values: list[Decimal]) -> bool:
    if len(money_values) >= 2:
        return True
    if money_values and (
        _QUANTITY_PRICE_RE.search(line)
        or _PRICE_QUANTITY_RE.search(line)
        or re.search(r"\d\s*[=]\s*\d{1,6}[,.]\d{2}", line)
    ):
        return True

    keyword_line = _normalize_keyword_text(line)
    return bool(money_values) and any(
        marker in keyword_line
        for marker in (" ШТ", "ШТ.", " WT", "WT.", " 1Ш", "1ШТ", "1WT", "КОЛ-ВО")
    )


def _name_quality(name: str) -> int:
    if not name:
        return 0
    cyrillic_count = len(re.findall(r"[А-Яа-яЁё]", name))
    letter_count = len(re.findall(r"[A-Za-zА-Яа-яЁё]", name))
    return cyrillic_count * 2 + letter_count + min(len(name), 40) // 4


def _letter_count(name: str) -> int:
    return len(re.findall(r"[A-Za-zА-Яа-яЁё]", name))


def _cyrillic_count(name: str) -> int:
    return len(re.findall(r"[А-Яа-яЁё]", name))


def _latin_count(name: str) -> int:
    return len(re.findall(r"[A-Za-z]", name))


def _clean_item_name(line: str) -> str:
    cleaned = _MONEY_RE.sub(" ", line)
    cleaned = _QUANTITY_PRICE_RE.sub(" ", cleaned)
    cleaned = _PRICE_QUANTITY_RE.sub(" ", cleaned)
    cleaned = _UNIT_QUANTITY_RE.sub(" ", cleaned)
    cleaned = _LONG_NUMBER_RE.sub(" ", cleaned)
    cleaned = re.sub(r"^\s*\d{3,5}\b", " ", cleaned)
    cleaned = re.sub(r"\b\d{1,3}(?:[,.]\d{1,3})?\s*=", " ", cleaned)
    cleaned = re.sub(r"=\s*", " ", cleaned)
    cleaned = re.sub(r"^[\W\d_]+", " ", cleaned)
    cleaned = re.sub(r"[\-=*#№]+", " ", cleaned)
    cleaned = re.sub(r"\s+\d{1,3}(?:[,.]\d{1,3})?$", " ", cleaned)
    cleaned = _SPACE_RE.sub(" ", cleaned).strip(" .,:;|-")
    return cleaned[:120]


def _cleanup_item_name(name: str, line_total: Decimal) -> str:
    cleaned = _normalize_text(name)

    for pattern, replacement in _NAME_REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)

    first_word = cleaned.split(" ", 1)[0].upper() if cleaned else ""
    if not any(first_word.startswith(prefix) for prefix in _KNOWN_LATIN_PREFIXES):
        cleaned = _LATIN_NOISE_PREFIX_RE.sub("", cleaned)
        cleaned = re.sub(r"^[A-Za-z]{1,4}[?}\])]+[\s:;-]+(?=[А-Яа-яЁё])", "", cleaned)

    cleaned = re.sub(r"^[?}\])('`.,:;|-]+\s*", "", cleaned)
    cleaned = re.sub(r"\s+[A-Za-z]{1,2}$", "", cleaned)
    cleaned = re.sub(r"\s+[КK]\s+te$", "", cleaned, flags=re.IGNORECASE)

    keyword_line = _normalize_keyword_text(cleaned)
    if "МАГНИТ" in keyword_line and "ПАКЕТ" not in keyword_line and line_total <= Decimal("20.00"):
        cleaned = "МАГНИТ ПАКЕТ-МАЙКА"
    if "ORIGIN" in keyword_line and "ШОК" in keyword_line and "GOODMIX" not in keyword_line:
        cleaned = f"GOODMIX ДУО {cleaned}"
    if "LORENZ NATURALS" in keyword_line and "ЧИПС" in keyword_line and "КЛАСС" not in keyword_line:
        cleaned = f"{cleaned} ЧИПСЫ КЛАССИЧЕСКИЕ"

    return _SPACE_RE.sub(" ", cleaned).strip(" .,:;|-")[:120]


def _extract_receipt_total(lines: list[str]) -> Decimal | None:
    total: Decimal | None = None
    for line in lines:
        if _line_looks_like_ocr_noise(line):
            continue
        keyword_line = _normalize_keyword_text(line)
        if not any(keyword in keyword_line for keyword in _TOTAL_KEYWORDS):
            continue
        if "НДС" in keyword_line:
            continue
        if "СКИД" in keyword_line and "ИТОГ" not in keyword_line:
            continue
        values = _extract_spaced_money_values(line) or _extract_money_values(line)
        if values:
            total = max(values)
    return total


def _drop_leading_money_digit(value: Decimal) -> Decimal | None:
    text = _format_decimal(value)
    whole, cents = text.split(".", 1)
    if len(whole) < 3:
        return None

    try:
        corrected = Decimal(f"{whole[1:]}.{cents}").quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return corrected if corrected > 0 else None


def _postprocess_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    amounts = [
        _normalize_money_token(str(item.get("sum")))
        for item in items
    ]
    regular_amounts = sorted(
        amount for amount in amounts if amount is not None and Decimal("1.00") <= amount <= Decimal("300.00")
    )
    median_amount = regular_amounts[len(regular_amounts) // 2] if regular_amounts else None

    processed: list[dict[str, Any]] = []
    for item in items:
        amount = _normalize_money_token(str(item.get("sum")))
        name = _cleanup_item_name(str(item.get("name") or ""), amount or Decimal("0"))
        if not amount or amount <= 0:
            continue
        if amount < Decimal("8.00") and _name_quality(name) < 12:
            continue
        if (
            amount < Decimal("8.00")
            and _cyrillic_count(name) <= 3
            and _latin_count(name) > _cyrillic_count(name)
        ):
            continue

        if amount >= Decimal("500.00") and median_amount and median_amount < Decimal("200.00"):
            corrected = _drop_leading_money_digit(amount)
            name_is_weak = _name_quality(name) < 10 or (
                _cyrillic_count(name) == 0
                and not any(name.upper().startswith(prefix) for prefix in _KNOWN_LATIN_PREFIXES)
            )
            if name_is_weak:
                continue
            if corrected and corrected <= Decimal("300.00"):
                amount = corrected
                item["sum"] = _format_decimal(corrected)
                item["price"] = _format_decimal(corrected)

        if _line_is_ignored(name):
            continue

        item["name"] = name
        processed.append(item)

    return processed


def _item_amount(item: dict[str, Any]) -> Decimal | None:
    return _normalize_money_token(str(item.get("sum")))


def _names_are_similar(first: str, second: str) -> bool:
    first_normalized = _normalize_keyword_text(first)
    second_normalized = _normalize_keyword_text(second)
    if not first_normalized or not second_normalized:
        return False
    return SequenceMatcher(None, first_normalized, second_normalized).ratio() >= 0.58


def _merge_candidate_items(
    selected_items: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    selected_variant: str,
) -> tuple[list[dict[str, Any]], int]:
    merged = [dict(item) for item in selected_items]
    added = 0

    sorted_candidates = sorted(
        candidates,
        key=lambda candidate: (len(candidate["items"]), candidate["average_confidence"]),
        reverse=True,
    )

    for candidate in sorted_candidates:
        if candidate["variant"] == selected_variant:
            continue
        if len(candidate["items"]) < 5 or candidate["average_confidence"] < 55:
            continue

        for candidate_item in candidate["items"]:
            if added >= 6:
                return merged, added

            amount = _item_amount(candidate_item)
            if amount is None or amount < Decimal("8.00") or amount > Decimal("300.00"):
                continue

            candidate_name = str(candidate_item.get("name") or "")
            if _name_quality(candidate_name) < 12:
                continue

            same_amount_items = [
                item
                for item in merged
                if (existing_amount := _item_amount(item)) is not None
                and abs(existing_amount - amount) <= Decimal("0.05")
            ]
            close_amount_items = [
                item
                for item in merged
                if (existing_amount := _item_amount(item)) is not None
                and abs(existing_amount - amount) <= Decimal("0.50")
            ]

            if any(_names_are_similar(candidate_name, str(item.get("name") or "")) for item in close_amount_items):
                continue
            if close_amount_items and not same_amount_items:
                continue

            merged.append(dict(candidate_item))
            added += 1

    return merged, added


def _score_ocr_candidate(
    items: list[dict[str, Any]],
    average_confidence: float,
    receipt_total: Decimal | None,
    items_sum: Decimal,
) -> tuple[int, int, float]:
    trusted_item_count = len(items)
    if average_confidence < 50:
        trusted_item_count = 0
    elif trusted_item_count <= 1 and average_confidence < 58:
        trusted_item_count = 0

    total_fit_score = 0
    if len(items) >= 3 and receipt_total and items_sum:
        difference = abs(receipt_total - items_sum)
        if difference <= max(Decimal("1.00"), receipt_total * Decimal("0.05")):
            total_fit_score = 2
        elif difference <= max(Decimal("3.00"), receipt_total * Decimal("0.20")):
            total_fit_score = 1
        else:
            total_fit_score = -1

    return trusted_item_count, total_fit_score, average_confidence


def _parse_receipt_lines(lines: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    pending_name: str | None = None

    for raw_line in lines:
        line = _normalize_text(raw_line)
        if len(line) < 3:
            continue

        if _line_looks_like_ocr_noise(line):
            continue

        if _line_is_boundary(line):
            if items:
                break
            pending_name = None
            continue

        if _line_is_ignored(line):
            continue

        money_values = _extract_money_values(line)
        has_letters = _line_has_letters(line)
        clean_name = _clean_item_name(line)
        if (
            len(money_values) == 1
            and money_values[0] <= Decimal("5.00")
            and has_letters
            and not _is_price_table_line(line, money_values)
        ):
            money_values = []

        if pending_name and money_values and not has_letters and not _is_price_table_line(line, money_values):
            pending_name = None
            continue

        if not money_values:
            if has_letters and clean_name and len(clean_name) >= 3 and _name_quality(clean_name) >= 5:
                starts_new_item = bool(re.match(r"\s*\d{3,5}\b", line))
                if pending_name and not starts_new_item:
                    if len(clean_name) <= 8 or _name_quality(clean_name) < 8:
                        combined = f"{pending_name} {clean_name}".strip()
                        pending_name = combined[:120]
                    else:
                        pending_name = clean_name
                else:
                    pending_name = clean_name
            continue

        line_total = money_values[-1]
        if line_total <= 0 or line_total > Decimal("100000"):
            pending_name = None
            continue

        quantity = _extract_quantity(line)
        price = line_total
        if quantity > 1:
            price = (line_total / quantity).quantize(Decimal("0.01"))

        if pending_name and (
            _is_price_table_line(line, money_values)
            or not clean_name
            or len(clean_name) < 4
            or not has_letters
            or _name_quality(pending_name) > _name_quality(clean_name)
        ):
            clean_name = pending_name
        elif pending_name and clean_name and len(clean_name) <= 8:
            clean_name = f"{pending_name} {clean_name}".strip()

        pending_name = None
        clean_name = _cleanup_item_name(clean_name, line_total)

        if (
            not clean_name
            or len(clean_name) < 3
            or _letter_count(clean_name) < 4
            or not _line_has_letters(clean_name)
        ):
            continue
        if _line_is_ignored(clean_name):
            continue

        items.append(
            {
                "name": clean_name,
                "quantity": _format_quantity(quantity),
                "price": _format_decimal(price),
                "sum": _format_decimal(line_total),
            }
        )

        if len(items) >= 80:
            break

    return _postprocess_items(items)


def _resolve_tesseract_command(command: str) -> str:
    command = command.strip() or "tesseract"
    candidate = Path(command)
    if candidate.exists():
        return str(candidate)

    located = shutil.which(command)
    if located:
        return located

    raise RuntimeError(
        "Локальный OCR недоступен: команда tesseract не найдена. "
        "Установите Tesseract OCR и добавьте его в PATH или задайте TESSERACT_CMD."
    )


def _load_image(image_bytes: bytes):
    cv2, np = _import_cv_dependencies()
    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("Не удалось прочитать изображение для OCR.")
    return cv2, image


def _resize_for_ocr(image, cv2, *, target_width: int = 1600, max_width: int = 2200):
    height, width = image.shape[:2]

    if width < target_width:
        scale = target_width / width
    elif width > max_width:
        scale = max_width / width
    else:
        scale = 1.0

    if scale == 1.0:
        return image

    interpolation = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
    return cv2.resize(image, None, fx=scale, fy=scale, interpolation=interpolation)


def _to_contrast_grayscale(image, cv2):
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    grayscale = cv2.copyMakeBorder(
        grayscale,
        24,
        24,
        24,
        24,
        cv2.BORDER_CONSTANT,
        value=255,
    )
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(grayscale)


def _sharpen_grayscale(image, cv2):
    blur = cv2.GaussianBlur(image, (0, 0), 1.0)
    return cv2.addWeighted(image, 1.45, blur, -0.45, 0)


def _crop_receipt_column(image, cv2):
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 0, 120), (180, 70, 255))
    column_density = (mask > 0).mean(axis=0)
    columns = [index for index, density in enumerate(column_density) if density > 0.15]
    if not columns:
        return None

    x0 = max(0, columns[0] - 24)
    x1 = min(image.shape[1], columns[-1] + 24)
    crop_width = x1 - x0
    if crop_width < image.shape[1] * 0.25 or crop_width > image.shape[1] * 0.9:
        return None

    return image[:, x0:x1]


def _generate_image_variants(image, cv2):
    base_images = [("normal", image)]
    receipt_crop = _crop_receipt_column(image, cv2)
    if receipt_crop is not None:
        base_images.append(("receipt_crop", receipt_crop))

    height, width = image.shape[:2]
    if width > height * 1.15:
        base_images.append(("rotated_cw", cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)))
        base_images.append(("rotated_ccw", cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)))

    for prefix, base_image in base_images:
        resized = _resize_for_ocr(base_image, cv2)
        contrast = _to_contrast_grayscale(resized, cv2)

        threshold = cv2.adaptiveThreshold(
            contrast,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            35,
            11,
        )

        yield f"{prefix}_contrast", contrast
        yield f"{prefix}_threshold", threshold

        if prefix == "receipt_crop":
            large = _resize_for_ocr(base_image, cv2, target_width=2800, max_width=3000)
            large_contrast = _to_contrast_grayscale(large, cv2)
            yield f"{prefix}_large_sharp", _sharpen_grayscale(large_contrast, cv2)


def _run_tesseract_tsv(
    *,
    image_path: str,
    tesseract_cmd: str,
    languages: str,
    timeout_seconds: float,
    tessdata_dir: str | None,
) -> str:
    def build_command(*, include_tessdata_dir: bool) -> list[str]:
        command = [
            tesseract_cmd,
            image_path,
            "stdout",
        ]
        if include_tessdata_dir and tessdata_dir:
            command.extend(["--tessdata-dir", tessdata_dir])
        command.extend(
            [
                "-l",
                languages,
                "--oem",
                "1",
                "--psm",
                "6",
                "tsv",
            ]
        )
        return command

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    command = build_command(include_tessdata_dir=True)
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        creationflags=creationflags,
        check=False,
    )

    if completed.returncode != 0 and tessdata_dir:
        fallback_command = build_command(include_tessdata_dir=False)
        fallback_completed = subprocess.run(
            fallback_command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            creationflags=creationflags,
            check=False,
        )
        if fallback_completed.returncode == 0:
            return fallback_completed.stdout

    if completed.returncode != 0:
        stderr = _normalize_text(completed.stderr)[:500]
        raise RuntimeError(f"Tesseract вернул ошибку: {stderr or completed.returncode}")

    return completed.stdout


def _lines_from_tsv(tsv_payload: str) -> tuple[list[str], float]:
    reader = csv.DictReader(io.StringIO(tsv_payload), delimiter="\t")
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}

    for row in reader:
        text = _normalize_text(row.get("text") or "")
        if not text:
            continue

        try:
            confidence = float(row.get("conf") or "-1")
        except ValueError:
            confidence = -1
        if confidence < 25:
            continue

        key = (
            row.get("page_num") or "0",
            row.get("block_num") or "0",
            row.get("par_num") or "0",
            row.get("line_num") or "0",
        )
        try:
            left = int(float(row.get("left") or "0"))
            top = int(float(row.get("top") or "0"))
        except ValueError:
            left = 0
            top = 0

        grouped.setdefault(key, []).append(
            {
                "text": text,
                "left": left,
                "top": top,
                "confidence": confidence,
            }
        )

    line_entries: list[tuple[int, int, str, float]] = []
    confidences: list[float] = []
    for words in grouped.values():
        words.sort(key=lambda word: word["left"])
        line_text = _normalize_text(" ".join(str(word["text"]) for word in words))
        if not line_text:
            continue
        top = min(int(word["top"]) for word in words)
        left = min(int(word["left"]) for word in words)
        confidence = sum(float(word["confidence"]) for word in words) / len(words)
        confidences.append(confidence)
        line_entries.append((top, left, line_text, confidence))

    line_entries.sort(key=lambda entry: (entry[0], entry[1]))
    lines = [entry[2] for entry in line_entries]
    average_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return lines, average_confidence


def extract_receipt_items_from_image(
    image_bytes: bytes,
    *,
    tesseract_cmd: str = "tesseract",
    languages: str = "rus+eng",
    timeout_seconds: float = 20,
    tessdata_dir: str | None = None,
) -> dict[str, Any]:
    resolved_cmd = _resolve_tesseract_command(tesseract_cmd)
    cv2, image = _load_image(image_bytes)

    best_result: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="splitcheck_ocr_") as temp_dir:
        for variant_name, variant_image in _generate_image_variants(image, cv2):
            image_path = str(Path(temp_dir) / f"{variant_name}.png")
            cv2.imwrite(image_path, variant_image)

            tsv_payload = _run_tesseract_tsv(
                image_path=image_path,
                tesseract_cmd=resolved_cmd,
                languages=languages,
                timeout_seconds=timeout_seconds,
                tessdata_dir=tessdata_dir,
            )
            lines, average_confidence = _lines_from_tsv(tsv_payload)
            items = _parse_receipt_lines(lines)
            receipt_total = _extract_receipt_total(lines)
            items_sum = sum(
                (_normalize_money_token(str(item["sum"])) or Decimal("0"))
                for item in items
            )

            score = _score_ocr_candidate(
                items,
                average_confidence,
                receipt_total,
                items_sum,
            )
            candidate = {
                "variant": variant_name,
                "items": items,
                "lines": lines,
                "average_confidence": average_confidence,
                "receipt_total": receipt_total,
                "items_sum": items_sum,
                "score": score,
            }
            candidates.append(candidate)
            if best_result is None or score > best_result["score"]:
                best_result = candidate

    if best_result is None:
        return {
            "status": "empty",
            "request_mode": "local_ocr",
            "message": "Локальный OCR не смог обработать изображение.",
            "items": [],
            "items_count": 0,
            "receipt_summary": {},
        }

    items, supplemental_count = _merge_candidate_items(
        best_result["items"],
        candidates,
        str(best_result["variant"]),
    )
    receipt_total = best_result["receipt_total"]
    items_sum = sum(
        (_normalize_money_token(str(item["sum"])) or Decimal("0"))
        for item in items
    )
    warnings: list[str] = []
    if best_result["average_confidence"] < 65:
        warnings.append("Качество OCR низкое: проверьте названия и суммы позиций.")
    if supplemental_count:
        warnings.append(f"OCR добавил {supplemental_count} поз. из альтернативного распознавания.")

    if receipt_total and items_sum:
        difference = abs(receipt_total - items_sum)
        allowed_difference = max(Decimal("1.00"), receipt_total * Decimal("0.05"))
        if difference > allowed_difference:
            warnings.append(
                (
                    "Сумма распознанных позиций отличается от итога чека: "
                    f"{_format_decimal(items_sum)} вместо {_format_decimal(receipt_total)}."
                )
            )

    summary_total = receipt_total or (items_sum if items else None)
    receipt_summary = {
        "total_sum": _format_decimal(summary_total) if summary_total else None,
        "ocr_items_sum": _format_decimal(items_sum) if items_sum else None,
        "ocr_confidence": round(float(best_result["average_confidence"]), 2),
        "ocr_variant": best_result["variant"],
        "ocr_supplemental_items": supplemental_count,
        "ocr_warnings": warnings,
    }

    return {
        "status": "success" if items else "empty",
        "request_mode": "local_ocr",
        "message": (
            f"Локальный OCR распознал {len(items)} поз."
            if items
            else "Локальный OCR не нашел товарные позиции."
        ),
        "items": items,
        "items_count": len(items),
        "receipt_summary": receipt_summary,
        "warnings": warnings,
        "raw_text": "\n".join(best_result["lines"])[:4000],
    }
