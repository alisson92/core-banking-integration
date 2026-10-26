"""Translate domain errors into RFC 9457 'problem details' responses."""

from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core_integration.domain.errors import (
    AccountNotFound,
    BusinessRuleViolation,
    CoreProtocolError,
    CoreUnavailable,
    DomainError,
    IdempotencyConflict,
    InvalidRequest,
    TransferNotFound,
    Unauthorized,
)
from core_integration.observability.structured_logging import fields, request_id_var

logger = logging.getLogger(__name__)


def status_for(exc: DomainError) -> int:
    # Order matters: AccountNotFound is also a BusinessRuleViolation.
    if isinstance(exc, Unauthorized):
        return 401
    if isinstance(exc, (AccountNotFound, TransferNotFound)):
        return 404
    if isinstance(exc, InvalidRequest):
        return 400
    if isinstance(exc, (BusinessRuleViolation, IdempotencyConflict)):
        return 422
    if isinstance(exc, CoreUnavailable):
        return 503
    if isinstance(exc, CoreProtocolError):
        return 502
    return 500


def problem(
    status: int, code: str, detail: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        headers=headers,
        content={
            "type": "about:blank",
            "title": HTTPStatus(status).phrase,
            "status": status,
            "detail": detail,
            "code": code,
            "request_id": request_id_var.get(),
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        status = status_for(exc)
        headers = {"Retry-After": "5"} if status == 503 else None
        if status >= 500:
            logger.error("request failed", extra=fields(code=exc.code, reason=exc.message))
        return problem(status, exc.code, exc.message, headers)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unexpected error")
        # Never leak internals to the caller.
        return problem(500, "INTERNAL_ERROR", "an unexpected error happened")
