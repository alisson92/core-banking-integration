"""HTTP face of the mock core banking system.

Run it with:
    uvicorn core_banking_mock.main:create_app --factory --port 8081
"""

from __future__ import annotations

import asyncio
import os
import random
import secrets
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .faults import FaultConfig
from .store import AccountRecord, CoreError, CoreStore, EntryRecord, TransferRecord

DEFAULT_API_KEY = "core-dev-key"


# ---------------------------------------------------------------- wire helpers
def _money(value: Decimal) -> str:
    return f"{value:.2f}"


def _account_wire(a: AccountRecord) -> dict[str, str]:
    return {
        "ACCT_NO": a.acct_no,
        "CUST_NM": a.cust_nm,
        "CCY_CD": a.ccy_cd,
        "STATUS_CD": a.status_cd,
    }


def _balance_wire(a: AccountRecord) -> dict[str, str]:
    return {
        "ACCT_NO": a.acct_no,
        "AVAIL_BAL": _money(a.balance),
        "LEDGER_BAL": _money(a.balance),
        "CCY_CD": a.ccy_cd,
        "AS_OF": datetime.now().strftime("%Y%m%d%H%M%S"),
    }


def _entry_wire(e: EntryRecord) -> dict[str, str]:
    return {
        "TXN_ID": e.txn_id,
        "ACCT_NO": e.acct_no,
        "DR_CR": e.dr_cr,
        "AMT": _money(e.amt),
        "CCY_CD": e.ccy_cd,
        "POST_DT": e.post_dt,
        "NARR": e.narr,
    }


def _transfer_wire(t: TransferRecord) -> dict[str, str]:
    return {"REF_ID": t.ref_id, "TXN_ID": t.txn_id, "STATUS_CD": t.status_cd}


class TransferIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ref_id: str = Field(alias="REF_ID")
    from_acct: str = Field(alias="FROM_ACCT")
    to_acct: str = Field(alias="TO_ACCT")
    amt: Decimal = Field(alias="AMT")
    ccy_cd: str = Field(default="BRL", alias="CCY_CD")


class FaultsIn(BaseModel):
    latency_ms: int = Field(default=0, ge=0)
    error_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    fail_next: int = Field(default=0, ge=0)
    slow_after_commit_ms: int = Field(default=0, ge=0)
    slow_after_commit_next: int = Field(default=0, ge=0)


# ---------------------------------------------------------------- dependencies
async def authenticate(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    expected: str = request.app.state.api_key
    if x_api_key is None or not secrets.compare_digest(x_api_key.encode(), expected.encode()):
        raise CoreError(401, "UNAUTHORIZED", "invalid or missing API key")


async def inject_faults(request: Request) -> None:
    faults: FaultConfig = request.app.state.faults
    if faults.latency_ms:
        await asyncio.sleep(faults.latency_ms / 1000)
    if faults.fail_next > 0:
        faults.fail_next -= 1
        raise CoreError(503, "UNAVAILABLE", "injected failure (fail_next)")
    if faults.error_rate and random.random() < faults.error_rate:
        raise CoreError(500, "INTERNAL", "injected random failure (error_rate)")


# --------------------------------------------------------------------- routers
core = APIRouter(prefix="/core/v1", dependencies=[Depends(authenticate), Depends(inject_faults)])
admin = APIRouter(prefix="/admin", dependencies=[Depends(authenticate)])
ops = APIRouter()


@core.get("/accounts/{acct_no}")
async def get_account(acct_no: str, request: Request) -> dict[str, str]:
    store: CoreStore = request.app.state.store
    return _account_wire(store.get_account(acct_no))


@core.get("/accounts/{acct_no}/balance")
async def get_balance(acct_no: str, request: Request) -> dict[str, str]:
    store: CoreStore = request.app.state.store
    return _balance_wire(store.get_account(acct_no))


@core.get("/accounts/{acct_no}/transactions")
async def get_transactions(
    acct_no: str,
    request: Request,
    from_dt: str = Query(alias="FROM_DT", pattern=r"^\d{8}$"),
    to_dt: str = Query(alias="TO_DT", pattern=r"^\d{8}$"),
) -> dict[str, object]:
    store: CoreStore = request.app.state.store
    entries = store.entries_between(acct_no, from_dt, to_dt)
    return {"ACCT_NO": acct_no, "TXNS": [_entry_wire(e) for e in entries]}


@core.post("/transfers")
async def create_transfer(body: TransferIn, request: Request) -> dict[str, str]:
    store: CoreStore = request.app.state.store
    faults: FaultConfig = request.app.state.faults
    record = store.transfer(body.ref_id, body.from_acct, body.to_acct, body.amt, body.ccy_cd)
    # The money has moved. Now we may be slow to answer (see FaultConfig).
    if faults.slow_after_commit_next > 0:
        faults.slow_after_commit_next -= 1
        await asyncio.sleep(faults.slow_after_commit_ms / 1000)
    return _transfer_wire(record)


@core.get("/transfers/{ref_id}")
async def get_transfer(ref_id: str, request: Request) -> dict[str, str]:
    store: CoreStore = request.app.state.store
    return _transfer_wire(store.get_transfer(ref_id))


@admin.get("/faults")
async def read_faults(request: Request) -> dict[str, float | int]:
    return request.app.state.faults.as_dict()


@admin.post("/faults")
async def set_faults(body: FaultsIn, request: Request) -> dict[str, float | int]:
    faults: FaultConfig = request.app.state.faults
    faults.latency_ms = body.latency_ms
    faults.error_rate = body.error_rate
    faults.fail_next = body.fail_next
    faults.slow_after_commit_ms = body.slow_after_commit_ms
    faults.slow_after_commit_next = body.slow_after_commit_next
    return faults.as_dict()


@admin.delete("/faults")
async def clear_faults(request: Request) -> dict[str, float | int]:
    request.app.state.faults.reset()
    return request.app.state.faults.as_dict()


@admin.post("/reset")
async def reset_everything(request: Request) -> dict[str, str]:
    request.app.state.store.reset()
    request.app.state.faults.reset()
    return {"status": "reset"}


@ops.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@ops.get("/health/ready")
async def ready() -> dict[str, str]:
    return {"status": "ok"}


# ------------------------------------------------------------------ app factory
def create_app(api_key: str | None = None) -> FastAPI:
    app = FastAPI(title="Mock Core Banking", version="0.1.0")
    app.state.api_key = api_key or os.getenv("CORE_MOCK_API_KEY", DEFAULT_API_KEY)
    app.state.store = CoreStore()
    app.state.faults = FaultConfig()

    @app.exception_handler(CoreError)
    async def core_error_handler(_: Request, exc: CoreError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status, content={"ERR_CD": exc.code, "ERR_MSG": exc.message}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400, content={"ERR_CD": "BAD_REQUEST", "ERR_MSG": "invalid request payload"}
        )

    app.include_router(core)
    app.include_router(admin)
    app.include_router(ops)
    return app
