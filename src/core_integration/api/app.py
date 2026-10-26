"""FastAPI application factory.

Run it with:
    uvicorn core_integration.api.app:create_app --factory --port 8080
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI

from core_integration import __version__
from core_integration.api.errors import register_error_handlers
from core_integration.api.middleware import make_observability_middleware
from core_integration.api.routes import internal, ops, v1
from core_integration.bootstrap import Container, build_container
from core_integration.infrastructure.settings import DEFAULT_SERVICE_API_KEY, Settings
from core_integration.observability.structured_logging import configure_logging, fields

logger = logging.getLogger(__name__)


async def _reconcile_loop(container: Container) -> None:
    interval = container.settings.reconcile_interval_seconds
    min_age = container.settings.reconcile_min_age_seconds
    while True:
        await asyncio.sleep(interval)
        try:
            await container.transfers.reconcile_pending(min_age)
        except Exception:  # the loop must survive anything
            logger.exception("reconciliation run failed")


def create_app(
    settings: Settings | None = None,
    *,
    http_client: httpx.AsyncClient | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    container = build_container(settings, http_client=http_client, clock=clock)

    if settings.service_api_key.get_secret_value() == DEFAULT_SERVICE_API_KEY:
        logger.warning("using the default service API key: fine for a lab, never for production")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task: asyncio.Task[None] | None = None
        if settings.reconcile_interval_seconds > 0:
            task = asyncio.create_task(_reconcile_loop(container))
            logger.info(
                "reconciliation loop started",
                extra=fields(interval_s=settings.reconcile_interval_seconds),
            )
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            await container.http_client.aclose()

    app = FastAPI(
        title="Core Banking Integration",
        version=__version__,
        description="Practice project: an integration service in front of a (mock) core banking.",
        lifespan=lifespan,
    )
    app.state.container = container
    app.middleware("http")(make_observability_middleware(container.metrics))
    register_error_handlers(app)
    app.include_router(v1)
    app.include_router(internal)
    app.include_router(ops)
    return app
