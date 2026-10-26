"""JSON logs that never leak sensitive data.

Two protections:
1. The formatter masks account numbers and redacts secrets by KEY name.
2. Libraries that log full URLs (httpx logs the path, which contains the account
   number) are silenced to WARNING.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_SECRET_KEY_PARTS = ("api_key", "apikey", "authorization", "secret", "password", "token")
_HANDLER_TAG = "_core_integration_handler"


def mask_account(value: str) -> str:
    """Keep only the last 4 characters: '0001234567' -> '******4567'."""
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]


def sanitize(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(part in lowered for part in _SECRET_KEY_PARTS):
        return "[REDACTED]"
    if "account" in lowered and isinstance(value, str):
        return mask_account(value)
    return value


def fields(**kwargs: Any) -> dict[str, dict[str, Any]]:
    """Use as: logger.info("message", extra=fields(transfer_id=..., source_account=...))."""
    return {"fields": kwargs}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            for key, value in extra.items():
                payload[key] = sanitize(key, value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    # Replace only OUR handler, so calling this twice (or under pytest) is safe.
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_TAG, False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    setattr(handler, _HANDLER_TAG, True)
    root.addHandler(handler)

    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
