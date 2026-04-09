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
    )
