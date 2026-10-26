"""FastAPI dependencies: container access and API-key authentication."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Depends, Header, Request

from core_integration.bootstrap import Container
from core_integration.domain.errors import Unauthorized


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


async def require_api_key(
    container: Annotated[Container, Depends(get_container)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = container.settings.service_api_key.get_secret_value().encode()
    # compare_digest takes the same time whatever the input, so it leaks no timing hints.
    if x_api_key is None or not secrets.compare_digest(x_api_key.encode(), expected):
        raise Unauthorized("missing or invalid X-API-Key")
