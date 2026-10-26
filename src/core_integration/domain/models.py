"""Our domain model. The core's wire format never leaks into this file."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum

from core_integration.domain.errors import InvalidTransition
from core_integration.domain.money import Money


class AccountStatus(StrEnum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    CLOSED = "CLOSED"


class TransactionKind(StrEnum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"


class TransferStatus(StrEnum):
    PENDING = "PENDING"  # we do not know the final outcome yet
    CONFIRMED = "CONFIRMED"  # the core applied it
    FAILED = "FAILED"  # the core refused it


@dataclass(frozen=True, slots=True)
class Account:
    id: str
    holder_name: str
    currency: str
    status: AccountStatus


@dataclass(frozen=True, slots=True)
class Balance:
    account_id: str
    available: Money
    ledger: Money


@dataclass(frozen=True, slots=True)
class Transaction:
    id: str
    account_id: str
    kind: TransactionKind
    amount: Money
    booked_on: date
    description: str


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Transfer:
    """State machine: PENDING -> CONFIRMED or PENDING -> FAILED. Final states never change."""

    id: str
    idempotency_key: str
    request_hash: str
    source_account: str
    destination_account: str
    amount: Money
    core_reference: str  # sent to the core; it deduplicates on this value
    status: TransferStatus = TransferStatus.PENDING
    core_transaction_id: str | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    @classmethod
    def new(
        cls,
        *,
        idempotency_key: str,
        request_hash: str,
        source_account: str,
        destination_account: str,
        amount: Money,
        now: datetime | None = None,
    ) -> Transfer:
        transfer_id = uuid.uuid4()
        moment = now or _utcnow()
        return cls(
            id=str(transfer_id),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            source_account=source_account,
            destination_account=destination_account,
            amount=amount,
            # Legacy cores limit references to 20 characters: "TRF" + 17 hex chars.
            core_reference="TRF" + transfer_id.hex[:17],
            created_at=moment,
            updated_at=moment,
        )

    def confirm(self, core_transaction_id: str | None) -> None:
        self._require_pending("confirm")
        self.status = TransferStatus.CONFIRMED
        self.core_transaction_id = core_transaction_id
        self.updated_at = _utcnow()

    def fail(self, code: str, reason: str) -> None:
        self._require_pending("fail")
        self.status = TransferStatus.FAILED
        self.failure_code = code
        self.failure_reason = reason
        self.updated_at = _utcnow()

    def _require_pending(self, action: str) -> None:
        if self.status is not TransferStatus.PENDING:
            raise InvalidTransition(f"cannot {action} a transfer that is already {self.status}")
