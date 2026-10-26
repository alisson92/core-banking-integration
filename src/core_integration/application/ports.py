"""Ports: what the application needs from the outside world.

The application depends on these interfaces. Adapters implement them.
This is what lets us replace the core (or the database) without touching the use cases.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from core_integration.domain.models import Account, Balance, Transaction, Transfer, TransferStatus
from core_integration.domain.money import Money


@dataclass(frozen=True, slots=True)
class CoreTransferResult:
    reference: str
    status: TransferStatus
    core_transaction_id: str | None = None
    failure_code: str | None = None
    failure_reason: str | None = None


class CoreBankingGateway(Protocol):
    async def get_account(self, account_id: str) -> Account: ...

    async def get_balance(self, account_id: str) -> Balance: ...

    async def get_statement(self, account_id: str, start: date, end: date) -> list[Transaction]: ...

    async def submit_transfer(
        self, *, reference: str, source_account: str, destination_account: str, amount: Money
    ) -> CoreTransferResult:
        """Idempotent on `reference`: sending the same reference twice never moves money twice."""
        ...

    async def find_transfer(self, reference: str) -> CoreTransferResult | None:
        """Ask the core what happened to a reference. None means the core never saw it."""
        ...


class TransferRepository(Protocol):
    async def add(self, transfer: Transfer) -> None: ...

    async def update(self, transfer: Transfer) -> None: ...

    async def get(self, transfer_id: str) -> Transfer | None: ...

    async def get_by_idempotency_key(self, key: str) -> Transfer | None: ...

    async def list_pending(self, created_before: datetime) -> list[Transfer]: ...
