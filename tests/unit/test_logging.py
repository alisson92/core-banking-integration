import json
import logging

from core_integration.observability.structured_logging import (
    JsonFormatter,
    configure_logging,
    fields,
    mask_account,
    request_id_var,
)


def render(**kwargs) -> dict:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "hello", None, None)
    record.fields = kwargs
    return json.loads(JsonFormatter().format(record))


def test_mask_account_keeps_last_four():
    assert mask_account("0001234567") == "******4567"
    assert mask_account("123") == "***"


def test_formatter_masks_accounts_and_redacts_secrets():
    out = render(source_account="0001234567", api_key="top-secret", authorization="Bearer x")
    assert out["source_account"] == "******4567"
    assert out["api_key"] == "[REDACTED]"
    assert out["authorization"] == "[REDACTED]"


def test_formatter_keeps_harmless_fields_and_request_id():
    token = request_id_var.set("req-1")
    try:
        out = render(status=200, route="/v1/x")
    finally:
        request_id_var.reset(token)
    assert out["status"] == 200
    assert out["route"] == "/v1/x"
    assert out["request_id"] == "req-1"
    assert out["message"] == "hello"


def test_fields_helper_shape():
    assert fields(a=1) == {"fields": {"a": 1}}


def test_configure_logging_silences_libraries_that_log_urls_and_is_repeatable():
    configure_logging("INFO")
    configure_logging("INFO")
    ours = [
        h for h in logging.getLogger().handlers if getattr(h, "_core_integration_handler", False)
    ]
    assert len(ours) == 1
    assert logging.getLogger("httpx").level == logging.WARNING
