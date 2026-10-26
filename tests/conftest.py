"""Shared fixtures.

The integration service talks to the mock core through httpx's ASGITransport, so tests run
in-process: no ports, no network, and still the full HTTP stack on both sides.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from core_banking_mock.main import create_app as create_core_app
from fastapi import FastAPI
from pydantic import SecretStr

from core_integration.api.app import create_app
from core_integration.bootstrap import Container
from core_integration.infrastructure.settings import Settings

CORE_KEY = "core-test-key"
SERVICE_KEY = "svc-test-key"

MARIA = "0001234567"  # starts with 5000.00
JOAO = "0007654321"  # starts with 1000.00
BLOCKED = "0009999999"
CLOSED = "0008888888"


class FakeClock:
    """A clock you control, so circuit-breaker tests never sleep."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass
class Harness:
    app: FastAPI
    client: httpx.AsyncClient
    clock: FakeClock

    @property
    def container(self) -> Container:
        container: Container = self.app.state.container
        return container

    async def balance(self, account: str) -> str:
        response = await self.client.get(f"/v1/accounts/{account}/balance")
        assert response.status_code == 200, response.text
        return str(response.json()["available"]["amount"])

    async def transfer(
        self, key: str, *, source: str = MARIA, destination: str = JOAO, amount: str = "100.00"
    ) -> httpx.Response:
        return await self.client.post(
            "/v1/transfers",
            headers={"Idempotency-Key": key},
            json={"source_account": source, "destination_account": destination, "amount": amount},
        )


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "core_base_url": "http://core.test",
        "core_api_key": SecretStr(CORE_KEY),
        "service_api_key": SecretStr(SERVICE_KEY),
        "core_timeout_seconds": 0.2,
        "read_max_attempts": 3,
        "write_max_attempts": 2,
        "backoff_base_seconds": 0.0,
        "backoff_max_seconds": 0.0,
        "breaker_failure_threshold": 3,
        "breaker_recovery_seconds": 30.0,
        "reconcile_interval_seconds": 0.0,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def core_app() -> FastAPI:
    return create_core_app(api_key=CORE_KEY)


@pytest.fixture
async def make_api(core_app: FastAPI) -> AsyncIterator[Callable[..., Awaitable[Harness]]]:
    opened: list[httpx.AsyncClient] = []

    async def _make(**overrides: Any) -> Harness:
        settings = make_settings(**overrides)
        core_http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=core_app), base_url=settings.core_base_url
        )
        clock = FakeClock()
        app = create_app(settings, http_client=core_http, clock=clock)
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://api.test",
            headers={"X-API-Key": SERVICE_KEY},
        )
        opened.extend([core_http, client])
        return Harness(app=app, client=client, clock=clock)

    yield _make
    for client in opened:
        await client.aclose()


@pytest.fixture
async def api(make_api: Callable[..., Awaitable[Harness]]) -> Harness:
    return await make_api()
