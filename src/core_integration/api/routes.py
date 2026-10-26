"""HTTP routes. Keep them thin: all rules live in the application layer."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response

from core_integration.api.dependencies import get_container, require_api_key
from core_integration.api.schemas import (
    ACCOUNT_ID_PATTERN,
    BalanceResponse,
    ReconcileResponse,
    StatementResponse,
    TransferRequest,
    TransferResponse,
    balance_response,
    transaction_out,
    transfer_response,
)
from core_integration.bootstrap import Container
from core_integration.domain.errors import InvalidRequest
from core_integration.domain.models import TransferStatus
from core_integration.domain.money import Money
from core_integration.observability.metrics import CONTENT_TYPE

Deps = Annotated[Container, Depends(get_container)]
AccountIdPath = Annotated[str, Path(pattern=ACCOUNT_ID_PATTERN)]

# --------------------------------------------------------------------- business API
v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)], tags=["banking"])


@v1.get("/accounts/{account_id}/balance", response_model=BalanceResponse)
async def get_balance(account_id: AccountIdPath, container: Deps) -> BalanceResponse:
    return balance_response(await container.accounts.get_balance(account_id))


@v1.get("/accounts/{account_id}/statement", response_model=StatementResponse)
async def get_statement(
    account_id: AccountIdPath,
    container: Deps,
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date, Query(alias="to")],
) -> StatementResponse:
    transactions = await container.accounts.get_statement(account_id, date_from, date_to)
    return StatementResponse(
        account_id=account_id,
        period_start=date_from,
        period_end=date_to,
        transactions=[transaction_out(t) for t in transactions],
    )


@v1.post("/transfers", response_model=TransferResponse)
async def create_transfer(
    body: TransferRequest,
    container: Deps,
    response: Response,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> TransferResponse:
    """201 = final outcome known (see `status`), 202 = still PENDING, 200 = replay of a key."""
    if not idempotency_key:
        raise InvalidRequest(
            "the Idempotency-Key header is required", code="MISSING_IDEMPOTENCY_KEY"
        )
    result = await container.transfers.create(
        idempotency_key=idempotency_key,
        source_account=body.source_account,
        destination_account=body.destination_account,
        amount=Money(body.amount, body.currency),
    )
    transfer = result.transfer
    if result.replayed:
        response.status_code = 200
        response.headers["Idempotent-Replayed"] = "true"
    else:
        response.status_code = 202 if transfer.status is TransferStatus.PENDING else 201
        response.headers["Location"] = f"/v1/transfers/{transfer.id}"
    return transfer_response(transfer)


@v1.get("/transfers/{transfer_id}", response_model=TransferResponse)
async def get_transfer(transfer_id: str, container: Deps) -> TransferResponse:
    return transfer_response(await container.transfers.get(transfer_id))


# ------------------------------------------------------------------- internal API
internal = APIRouter(prefix="/internal", dependencies=[Depends(require_api_key)], tags=["internal"])


@internal.post("/reconcile", response_model=ReconcileResponse)
async def reconcile(
    container: Deps,
    min_age_seconds: Annotated[float, Query(ge=0)] = 0.0,
) -> ReconcileResponse:
    report = await container.transfers.reconcile_pending(min_age_seconds)
    return ReconcileResponse(
        examined=report.examined,
        confirmed=report.confirmed,
        failed=report.failed,
        still_pending=report.still_pending,
        resubmitted=report.resubmitted,
    )


# ------------------------------------------------------------------------ ops (open)
ops = APIRouter(tags=["ops"])


@ops.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@ops.get("/health/ready")
async def ready(container: Deps) -> dict[str, str]:
    # Readiness does NOT fail when the core is down: taking every pod out of service during a
    # core outage would only make things worse. The circuit state is shown for humans.
    return {"status": "ok", "core_circuit": container.breaker.state.value}


@ops.get("/metrics")
async def metrics(container: Deps, request: Request) -> Response:
    return Response(content=container.metrics.render(), media_type=CONTENT_TYPE)
