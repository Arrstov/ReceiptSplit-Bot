from __future__ import annotations

from collections.abc import Iterable

def _import_cv_dependencies():
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "Для обработки QR-кодов не установлены зависимости OpenCV. "
            "Выполните 'pip install -r requirements.txt' в активированном .venv."
        ) from exc
    return cv2, np


def _generate_variants(image, cv2) -> Iterable:
    yield image

    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    yield grayscale

    upscaled = cv2.resize(
        grayscale,
        None,
        fx=1.7,
        fy=1.7,
        interpolation=cv2.INTER_CUBIC,
    )
    yield upscaled

    threshold = cv2.adaptiveThreshold(
        upscaled,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31,
        2,
    )
    yield threshold

    for variant in (image, grayscale, upscaled, threshold):
        yield cv2.rotate(variant, cv2.ROTATE_90_CLOCKWISE)
        yield cv2.rotate(variant, cv2.ROTATE_180)
        yield cv2.rotate(variant, cv2.ROTATE_90_COUNTERCLOCKWISE)


def decode_qr_from_image_bytes(image_bytes: bytes) -> str | None:
    if not image_bytes:
        return None

    cv2, np = _import_cv_dependencies()
    buffer = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        return None

    detector = cv2.QRCodeDetector()

    for variant in _generate_variants(image, cv2):
        data, points, _ = detector.detectAndDecode(variant)
        if points is not None and data:
            return data.strip()

        ok, decoded_info, _, _ = detector.detectAndDecodeMulti(variant)
        if ok and decoded_info:
            first_payload = next(
                (item.strip() for item in decoded_info if item and item.strip()),
                None,
            )
            if first_payload:
                return first_payload

    return None
