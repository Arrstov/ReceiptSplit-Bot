from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    ttl_seconds: int | None = 86400,
) -> dict[str, Any] | None:
    if not init_data:
        return None

    values = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = values.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(values.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        return None

    auth_date_raw = values.get("auth_date")
    if ttl_seconds is not None and auth_date_raw:
        try:
            auth_date = int(auth_date_raw)
        except ValueError:
            return None
        if time.time() - auth_date > ttl_seconds:
            return None

    user_raw = values.get("user")
    if user_raw:
        try:
            values["user"] = json.loads(user_raw)
        except json.JSONDecodeError:
            return None

    receiver_raw = values.get("receiver")
    if receiver_raw:
        try:
            values["receiver"] = json.loads(receiver_raw)
        except json.JSONDecodeError:
            return None

    return values

