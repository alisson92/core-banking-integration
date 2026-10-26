"""Request and response bodies of our public API (the contract is in api/openapi.yaml)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from core_integration.domain.models import Balance, Transaction, Transfer
from core_integration.domain.money import Money

ACCOUNT_ID_PATTERN = r"^\d{10}$"
AccountId = Annotated[str, StringConstraints(pattern=ACCOUNT_ID_PATTERN)]
CurrencyCode = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class MoneyOut(BaseModel):
    amount: str = Field(description="Decimal string with 2 places, e.g. '100.00'")
    currency: str


class BalanceResponse(BaseModel):
    account_id: str
    available: MoneyOut
    ledger: MoneyOut


class TransactionOut(BaseModel):
    id: str
    kind: str
    amount: MoneyOut
    booked_on: date
    description: str


class StatementResponse(BaseModel):
    account_id: str
    period_start: date
    period_end: date
    transactions: list[TransactionOut]


class TransferRequest(BaseModel):
    source_account: AccountId
    destination_account: AccountId
    amount: Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=2)]
    currency: CurrencyCode = "BRL"


class TransferResponse(BaseModel):
    id: str
    status: str
    source_account: str
    destination_account: str
    amount: MoneyOut
    failure_code: str | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class ReconcileResponse(BaseModel):
    examined: int
    confirmed: int
    failed: int
    still_pending: int
    resubmitted: int


def money_out(money: Money) -> MoneyOut:
    return MoneyOut(amount=money.to_wire(), currency=money.currency)


def balance_response(balance: Balance) -> BalanceResponse:
    return BalanceResponse(
        account_id=balance.account_id,
        available=money_out(balance.available),
        ledger=money_out(balance.ledger),
    )


def transaction_out(t: Transaction) -> TransactionOut:
    return TransactionOut(
        id=t.id,
        kind=t.kind.value,
        amount=money_out(t.amount),
        booked_on=t.booked_on,
        description=t.description,
    )


def transfer_response(t: Transfer) -> TransferResponse:
    return TransferResponse(
        id=t.id,
        status=t.status.value,
        source_account=t.source_account,
        destination_account=t.destination_account,
        amount=money_out(t.amount),
        failure_code=t.failure_code,
        failure_reason=t.failure_reason,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )
