import json
import logging

import pytest

from core_integration.observability.structured_logging import JsonFormatter
from tests.conftest import MARIA, SERVICE_KEY, Harness


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"/v1/accounts/{MARIA}/balance"),
        ("GET", f"/v1/accounts/{MARIA}/statement?from=2026-10-01&to=2026-10-31"),
        ("POST", "/v1/transfers"),
        ("GET", "/v1/transfers/abc"),
        ("POST", "/internal/reconcile"),
    ],
)
async def test_business_endpoints_require_the_api_key(api: Harness, method: str, path: str):
    for headers in ({"X-API-Key": "wrong"}, {"X-API-Key": ""}):
        response = await api.client.request(method, path, headers=headers)
        assert response.status_code == 401
        assert response.json()["code"] == "UNAUTHORIZED"


async def test_health_and_metrics_are_open(api: Harness):
    for path in ("/health/live", "/health/ready", "/metrics"):
        response = await api.client.get(path, headers={"X-API-Key": "wrong"})
        assert response.status_code == 200


async def test_metrics_expose_http_core_and_transfer_series(api: Harness):
    await api.transfer("obs-1")
    text = (await api.client.get("/metrics")).text
    assert 'http_requests_total{method="POST",route="/v1/transfers",status="201"}' in text
    assert 'core_requests_total{operation="submit_transfer",outcome="ok"}' in text
    assert 'transfers_total{status="CONFIRMED"}' in text
    assert "core_circuit_breaker_state 0.0" in text


async def test_request_id_is_echoed_when_provided(api: Harness):
    response = await api.client.get(
        f"/v1/accounts/{MARIA}/balance", headers={"X-Request-ID": "trace-me-123"}
    )
    assert response.headers["x-request-id"] == "trace-me-123"


async def test_logs_never_contain_account_numbers_or_keys(api: Harness, caplog):
    caplog.set_level(logging.DEBUG)
    await api.client.get(f"/v1/accounts/{MARIA}/balance")
    await api.transfer("obs-2")
    await api.client.get("/v1/accounts/9999999999/balance")

    formatter = JsonFormatter()
    lines = [formatter.format(record) for record in caplog.records]
    assert lines, "expected some log lines"
    everything = "\n".join(lines)
    assert MARIA not in everything
    assert "0007654321" not in everything
    assert SERVICE_KEY not in everything
    assert "core-test-key" not in everything
    # Access logs carry the route template, never the raw path.
    access = [json.loads(line) for line in lines if '"request"' in line]
    assert any(entry.get("route") == "/v1/accounts/{account_id}/balance" for entry in access)
