from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(slots=True)
class Settings:
    bot_token: str
    webapp_url: str
    backend_host: str
    backend_port: int
    log_level: str
    init_data_ttl_seconds: int
    proverkacheka_api_token: str | None
    proverkacheka_api_url: str
    proverkacheka_timeout_seconds: float
    local_ocr_enabled: bool
    tesseract_cmd: str
    tesseract_languages: str
    tesseract_timeout_seconds: float
    tesseract_tessdata_dir: str | None

    @property
    def normalized_webapp_url(self) -> str:
        return self.webapp_url.rstrip("/")


def _get_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or not value.strip():
        raise RuntimeError(f"Environment variable '{name}' is required.")
    return value.strip()


def _get_optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _get_bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_optional_path_env(name: str) -> str | None:
    value = _get_optional_env(name)
    if value is None:
        return None

    path = Path(value)
    if not path.is_absolute():
        path = BASE_DIR / path
    return str(path.resolve())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        bot_token=_get_env("BOT_TOKEN"),
        webapp_url=_get_env("WEBAPP_URL"),
        backend_host=os.getenv("BACKEND_HOST", "127.0.0.1"),
        backend_port=int(os.getenv("BACKEND_PORT", "8000")),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        init_data_ttl_seconds=int(os.getenv("INIT_DATA_TTL_SECONDS", "86400")),
        proverkacheka_api_token=_get_optional_env("PROVERKACHEKA_API_TOKEN"),
        proverkacheka_api_url=os.getenv(
            "PROVERKACHEKA_API_URL",
            "https://proverkacheka.com/api/v1/check/get",
        ).strip(),
        proverkacheka_timeout_seconds=float(
            os.getenv("PROVERKACHEKA_TIMEOUT_SECONDS", "20")
        ),
        local_ocr_enabled=_get_bool_env("LOCAL_OCR_ENABLED", True),
        tesseract_cmd=os.getenv("TESSERACT_CMD", "tesseract").strip() or "tesseract",
        tesseract_languages=os.getenv("TESSERACT_LANGUAGES", "rus+eng").strip() or "rus+eng",
        tesseract_timeout_seconds=float(os.getenv("TESSERACT_TIMEOUT_SECONDS", "20")),
        tesseract_tessdata_dir=_get_optional_path_env("TESSERACT_TESSDATA_DIR"),
    )
