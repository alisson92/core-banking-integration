"""Prometheus metrics. One registry per app instance (keeps tests isolated)."""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

CONTENT_TYPE = CONTENT_TYPE_LATEST

_BREAKER_VALUES = {"closed": 0, "half_open": 1, "open": 2}


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.http_requests = Counter(
            "http_requests_total",
            "HTTP requests served by this service",
            ["method", "route", "status"],
            registry=self.registry,
        )
        self.http_duration = Histogram(
            "http_request_duration_seconds",
            "Latency of HTTP requests served by this service",
            ["method", "route"],
            registry=self.registry,
        )
        self.core_requests = Counter(
            "core_requests_total",
            "Calls made to the core banking system",
            ["operation", "outcome"],
            registry=self.registry,
        )
        self.core_duration = Histogram(
            "core_request_duration_seconds",
            "Latency of calls to the core banking system",
            ["operation"],
            registry=self.registry,
        )
        self.breaker_state = Gauge(
            "core_circuit_breaker_state",
            "Circuit breaker state: 0=closed, 1=half_open, 2=open",
            registry=self.registry,
        )
        self.transfers = Counter(
            "transfers_total",
            "Transfers that reached a final state",
            ["status"],
            registry=self.registry,
        )
        self.breaker_state.set(0)

    def set_breaker_state(self, state: str) -> None:
        self.breaker_state.set(_BREAKER_VALUES[str(state)])

    def transfer_resolved(self, status: str) -> None:
        self.transfers.labels(status=status).inc()

    def render(self) -> bytes:
        return generate_latest(self.registry)
