"""Request id, access log and HTTP metrics in one middleware."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from core_integration.observability.metrics import Metrics
from core_integration.observability.structured_logging import fields, request_id_var

logger = logging.getLogger("core_integration.access")

_QUIET_PATHS = {"/metrics", "/health/live", "/health/ready"}


def make_observability_middleware(
    metrics: Metrics,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            elapsed = time.perf_counter() - started
            route = request.scope.get("route")
            # Use the route TEMPLATE ('/v1/accounts/{account_id}/balance'), never the raw path:
            # the raw path holds account numbers, and unbounded labels would blow up metrics.
            route_label = getattr(route, "path", "unmatched")
            metrics.http_requests.labels(request.method, route_label, str(status)).inc()
            metrics.http_duration.labels(request.method, route_label).observe(elapsed)
            level = logging.DEBUG if route_label in _QUIET_PATHS else logging.INFO
            logger.log(
                level,
                "request",
                extra=fields(
                    method=request.method,
                    route=route_label,
                    status=status,
                    duration_ms=round(elapsed * 1000, 1),
                ),
            )
            request_id_var.reset(token)

    return middleware
