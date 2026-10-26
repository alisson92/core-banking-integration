"""HTTP client for the core banking system: the only class that talks to the core.

Protections, from the inside out:
1. Timeout on every call (the core can hang).
2. Circuit breaker (stop hammering a core that is down).
3. Retry with backoff and jitter (absorb short glitches).
4. Error translation (the rest of the code never sees HTTP status codes).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any, TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel

from core_integration.adapters.corebanking import mappers
from core_integration.adapters.corebanking.wire import (
    AccountWire,
    BalanceWire,
    ErrorWire,
    StatementWire,
    TransferResultWire,
)
from core_integration.application.ports import CoreTransferResult
from core_integration.domain.errors import CircuitOpen, CoreProtocolError, CoreUnavailable
from core_integration.domain.models import Account, Balance, Transaction
from core_integration.domain.money import Money
from core_integration.infrastructure.resilience import CircuitBreaker, RetryPolicy
from core_integration.observability.metrics import Metrics
from core_integration.observability.structured_logging import fields

logger = logging.getLogger(__name__)

W = TypeVar("W", bound=BaseModel)
T = TypeVar("T")


class HttpCoreBankingClient:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        api_key: str,
        timeout: float,
        breaker: CircuitBreaker,
        read_policy: RetryPolicy,
        write_policy: RetryPolicy,
        metrics: Metrics | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: Callable[[], float] = random.random,
    ) -> None:
        self._http = http
        self._api_key = api_key
        self._timeout = timeout
        self._breaker = breaker
        self._read_policy = read_policy
        self._write_policy = write_policy
        self._metrics = metrics
        self._sleep = sleep
        self._rng = rng

    # ------------------------------------------------------------------ reads
    async def get_account(self, account_id: str) -> Account:
        response = await self._request(
            "get_account", "GET", f"/core/v1/accounts/{_id(account_id)}", policy=self._read_policy
        )
        self._raise_for_error(response)
        return self._parse(AccountWire, response, mappers.account_from_wire)

    async def get_balance(self, account_id: str) -> Balance:
        response = await self._request(
            "get_balance",
            "GET",
            f"/core/v1/accounts/{_id(account_id)}/balance",
            policy=self._read_policy,
        )
        self._raise_for_error(response)
        return self._parse(BalanceWire, response, mappers.balance_from_wire)

    async def get_statement(self, account_id: str, start: date, end: date) -> list[Transaction]:
        response = await self._request(
            "get_statement",
            "GET",
            f"/core/v1/accounts/{_id(account_id)}/transactions",
            policy=self._read_policy,
            params={"FROM_DT": start.strftime("%Y%m%d"), "TO_DT": end.strftime("%Y%m%d")},
        )
        self._raise_for_error(response)
        return self._parse(
            StatementWire,
            response,
            lambda w: [mappers.transaction_from_wire(t) for t in w.txns],
        )

    # ----------------------------------------------------------------- writes
    async def submit_transfer(
        self, *, reference: str, source_account: str, destination_account: str, amount: Money
    ) -> CoreTransferResult:
        body = {
            "REF_ID": reference,
            "FROM_ACCT": source_account,
            "TO_ACCT": destination_account,
            "AMT": amount.to_wire(),
            "CCY_CD": amount.currency,
        }
        response = await self._request(
            "submit_transfer",
            "POST",
            "/core/v1/transfers",
            policy=self._write_policy,
            json_body=body,
        )
        error = self._error(response)
        if response.status_code == 409 and error is not None and error.err_cd == "DUPLICATE_REF":
            # An earlier attempt DID reach the core (maybe we timed out waiting for the answer).
            # That is exactly why we send a reference: ask the core what happened to it.
            logger.info("core reports duplicate reference, fetching original result")
            existing = await self.find_transfer(reference)
            if existing is None:
                raise CoreProtocolError("core says the reference is duplicated but cannot find it")
            return existing
        self._raise_for_error(response)
        return self._parse(TransferResultWire, response, mappers.transfer_result_from_wire)

    async def find_transfer(self, reference: str) -> CoreTransferResult | None:
        response = await self._request(
            "find_transfer",
            "GET",
            f"/core/v1/transfers/{_id(reference)}",
            policy=self._read_policy,
        )
        error = self._error(response)
        if response.status_code == 404 and error is not None and error.err_cd == "REF_NOT_FOUND":
            return None
        self._raise_for_error(response)
        return self._parse(TransferResultWire, response, mappers.transfer_result_from_wire)

    # ---------------------------------------------------------------- plumbing
    async def _request(
        self,
        operation: str,
        method: str,
        path: str,
        *,
        policy: RetryPolicy,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        attempt = 0
        while True:
            attempt += 1
            try:
                return await self._send_once(
                    operation, method, path, params=params, json_body=json_body
                )
            except CircuitOpen:
                raise  # the breaker said stop: do not retry
            except CoreUnavailable as exc:
                if attempt >= policy.max_attempts:
                    raise
                delay = policy.delay(attempt, self._rng)
                logger.warning(
                    "core call failed, retrying",
                    extra=fields(
                        operation=operation,
                        attempt=attempt,
                        delay_s=round(delay, 3),
                        reason=str(exc),
                    ),
                )
                await self._sleep(delay)

    async def _send_once(
        self,
        operation: str,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None,
        json_body: dict[str, Any] | None,
    ) -> httpx.Response:
        self._breaker.before_call()
        started = time.perf_counter()
        try:
            # asyncio.timeout is a hard cap on the WHOLE call, on top of httpx's own timeouts.
            async with asyncio.timeout(self._timeout):
                response = await self._http.request(
                    method,
                    path,
                    params=params,
                    json=json_body,
                    headers={"X-API-Key": self._api_key},
                )
        except (TimeoutError, httpx.TimeoutException) as exc:
            self._breaker.record_failure()
            self._observe(operation, "timeout", started)
            raise CoreUnavailable("core timed out", outcome_unknown=True) from exc
        except httpx.TransportError as exc:
            self._breaker.record_failure()
            self._observe(operation, "connection_error", started)
            raise CoreUnavailable(
                "core is unreachable", outcome_unknown=not isinstance(exc, httpx.ConnectError)
            ) from exc
        except BaseException:
            self._breaker.abort_call()
            raise

        if response.status_code >= 500 or response.status_code == 429:
            self._breaker.record_failure()
            self._observe(operation, "server_error", started)
            raise CoreUnavailable(
                f"core answered HTTP {response.status_code}", outcome_unknown=True
            )

        # The core answered. Even a 4xx proves it is alive, so the breaker is happy.
        self._breaker.record_success()
        self._observe(operation, "ok" if response.status_code < 400 else "client_error", started)
        return response

    def _observe(self, operation: str, outcome: str, started: float) -> None:
        if self._metrics is None:
            return
        self._metrics.core_requests.labels(operation=operation, outcome=outcome).inc()
        self._metrics.core_duration.labels(operation=operation).observe(
            time.perf_counter() - started
        )

    @staticmethod
    def _error(response: httpx.Response) -> ErrorWire | None:
        try:
            return ErrorWire.model_validate(response.json())
        except ValueError:
            return None

    def _raise_for_error(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        error = self._error(response)
        if error is not None:
            mapped = mappers.error_from_code(error.err_cd, error.err_msg)
            if mapped is not None:
                raise mapped
        if response.status_code in (401, 403):
            raise CoreProtocolError("core rejected our credentials")
        raise CoreProtocolError(f"core answered an unexpected HTTP {response.status_code}")

    @staticmethod
    def _parse(model: type[W], response: httpx.Response, mapper: Callable[[W], T]) -> T:
        try:
            return mapper(model.model_validate(response.json()))
        except ValueError as exc:  # JSON errors, pydantic ValidationError and Money errors
            raise CoreProtocolError("core returned a payload we cannot understand") from exc


def _id(value: str) -> str:
    return quote(value, safe="")
