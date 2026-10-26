"""Composition root: the one place where concrete classes are wired together."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from core_integration.adapters.corebanking.client import HttpCoreBankingClient
from core_integration.application.accounts import AccountService
from core_integration.application.transfers import TransferService
from core_integration.infrastructure.memory_repository import InMemoryTransferRepository
from core_integration.infrastructure.resilience import CircuitBreaker, RetryPolicy
from core_integration.infrastructure.settings import Settings
from core_integration.observability.metrics import Metrics


@dataclass
class Container:
    settings: Settings
    metrics: Metrics
    breaker: CircuitBreaker
    http_client: httpx.AsyncClient
    accounts: AccountService
    transfers: TransferService


def build_container(
    settings: Settings,
    *,
    http_client: httpx.AsyncClient | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> Container:
    """`http_client` and `clock` can be injected, which is how the tests run without a network."""
    metrics = Metrics()
    breaker = CircuitBreaker(
        failure_threshold=settings.breaker_failure_threshold,
        recovery_timeout=settings.breaker_recovery_seconds,
        clock=clock,
        on_state_change=metrics.set_breaker_state,
    )
    http = http_client or httpx.AsyncClient(
        base_url=settings.core_base_url, timeout=settings.core_timeout_seconds
    )
    gateway = HttpCoreBankingClient(
        http,
        api_key=settings.core_api_key.get_secret_value(),
        timeout=settings.core_timeout_seconds,
        breaker=breaker,
        read_policy=RetryPolicy(
            settings.read_max_attempts, settings.backoff_base_seconds, settings.backoff_max_seconds
        ),
        write_policy=RetryPolicy(
            settings.write_max_attempts, settings.backoff_base_seconds, settings.backoff_max_seconds
        ),
        metrics=metrics,
    )
    return Container(
        settings=settings,
        metrics=metrics,
        breaker=breaker,
        http_client=http,
        accounts=AccountService(gateway),
        transfers=TransferService(
            gateway, InMemoryTransferRepository(), on_status=metrics.transfer_resolved
        ),
    )
