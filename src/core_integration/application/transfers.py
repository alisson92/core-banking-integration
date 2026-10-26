"""Transfer use cases: create (idempotent), read, and reconcile.

The heart of the project. Read docs/adr/0002 before changing anything here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from core_integration.application.ports import (
    CoreBankingGateway,
    CoreTransferResult,
    TransferRepository,
)
from core_integration.domain.errors import (
    BusinessRuleViolation,
    CoreProtocolError,
    CoreUnavailable,
    IdempotencyConflict,
    InvalidRequest,
    TransferNotFound,
)
from core_integration.domain.models import Transfer, TransferStatus
from core_integration.domain.money import Money
from core_integration.observability.structured_logging import fields

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CreateTransferResult:
    transfer: Transfer
    replayed: bool  # True when the same Idempotency-Key was already used


@dataclass(slots=True)
class ReconcileReport:
    examined: int = 0
    confirmed: int = 0
    failed: int = 0
    still_pending: int = 0
    resubmitted: int = 0


def _hash_request(source: str, destination: str, amount: Money) -> str:
    payload = json.dumps(
        {
            "source": source,
            "destination": destination,
            "amount": amount.to_wire(),
            "currency": amount.currency,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TransferService:
    def __init__(
        self,
        gateway: CoreBankingGateway,
        repository: TransferRepository,
        *,
        on_status: Callable[[str], None] | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._gateway = gateway
        self._repository = repository
        self._on_status = on_status or (lambda _status: None)
        self._clock = clock
        # Makes "check key, then store transfer" atomic inside this process.
        # With a real database this becomes a UNIQUE constraint on the key.
        self._create_lock = asyncio.Lock()

    # ----------------------------------------------------------------- create
    async def create(
        self,
        *,
        idempotency_key: str,
        source_account: str,
        destination_account: str,
        amount: Money,
    ) -> CreateTransferResult:
        if not idempotency_key or len(idempotency_key) > 255:
            raise InvalidRequest(
                "Idempotency-Key must have 1 to 255 characters", code="INVALID_IDEMPOTENCY_KEY"
            )
        if source_account == destination_account:
            raise InvalidRequest("source and destination accounts must differ", code="SAME_ACCOUNT")
        if not amount.is_positive():
            raise InvalidRequest("amount must be greater than zero", code="INVALID_AMOUNT")

        request_hash = _hash_request(source_account, destination_account, amount)

        async with self._create_lock:
            existing = await self._repository.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise IdempotencyConflict(
                        "this Idempotency-Key was already used with a different request"
                    )
                return CreateTransferResult(existing, replayed=True)

            transfer = Transfer.new(
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                source_account=source_account,
                destination_account=destination_account,
                amount=amount,
                now=self._clock(),
            )
            # Persist BEFORE calling the core: if we crash after the call, we still know
            # that this reference may exist in the core, and reconciliation can find it.
            await self._repository.add(transfer)

        await self._submit(transfer)
        return CreateTransferResult(transfer, replayed=False)

    async def get(self, transfer_id: str) -> Transfer:
        transfer = await self._repository.get(transfer_id)
        if transfer is None:
            raise TransferNotFound(f"transfer {transfer_id} not found")
        return transfer

    # -------------------------------------------------------------- reconcile
    async def reconcile_pending(self, min_age_seconds: float = 0.0) -> ReconcileReport:
        """Resolve PENDING transfers by asking the core what really happened.

        - core knows the reference -> copy its answer
        - core never saw it        -> submit again (safe: the core deduplicates on reference)
        - core unreachable         -> leave it PENDING and try again next time
        """
        cutoff = self._clock() - timedelta(seconds=min_age_seconds)
        pending = await self._repository.list_pending(created_before=cutoff)
        report = ReconcileReport(examined=len(pending))

        for transfer in pending:
            try:
                result = await self._gateway.find_transfer(transfer.core_reference)
                if result is None:
                    report.resubmitted += 1
                    result = await self._submit_to_core(transfer)
            except BusinessRuleViolation as exc:
                self._fail(transfer, exc)
            except (CoreUnavailable, CoreProtocolError):
                report.still_pending += 1
                continue
            else:
                self._apply(transfer, result)

            await self._repository.update(transfer)
            if transfer.status is TransferStatus.CONFIRMED:
                report.confirmed += 1
            elif transfer.status is TransferStatus.FAILED:
                report.failed += 1
            else:
                report.still_pending += 1

        logger.info("reconciliation finished", extra=fields(**vars_of(report)))
        return report

    # --------------------------------------------------------------- internals
    async def _submit_to_core(self, transfer: Transfer) -> CoreTransferResult:
        return await self._gateway.submit_transfer(
            reference=transfer.core_reference,
            source_account=transfer.source_account,
            destination_account=transfer.destination_account,
            amount=transfer.amount,
        )

    async def _submit(self, transfer: Transfer) -> None:
        try:
            result = await self._submit_to_core(transfer)
        except BusinessRuleViolation as exc:
            self._fail(transfer, exc)
        except (CoreUnavailable, CoreProtocolError) as exc:
            # We do NOT know if the money moved. Never guess: stay PENDING.
            logger.warning(
                "transfer left pending",
                extra=fields(
                    transfer_id=transfer.id,
                    reason=str(exc),
                    outcome_unknown=getattr(exc, "outcome_unknown", True),
                ),
            )
        else:
            self._apply(transfer, result)
        await self._repository.update(transfer)

    def _apply(self, transfer: Transfer, result: CoreTransferResult) -> None:
        if result.status is TransferStatus.CONFIRMED:
            transfer.confirm(result.core_transaction_id)
        elif result.status is TransferStatus.FAILED:
            transfer.fail(
                result.failure_code or "CORE_REJECTED",
                result.failure_reason or "rejected by the core",
            )
        self._announce(transfer)

    def _fail(self, transfer: Transfer, exc: BusinessRuleViolation) -> None:
        transfer.fail(exc.code, exc.message)
        self._announce(transfer)

    def _announce(self, transfer: Transfer) -> None:
        if transfer.status is TransferStatus.PENDING:
            return
        self._on_status(transfer.status.value)
        logger.info(
            "transfer resolved",
            extra=fields(
                transfer_id=transfer.id,
                status=transfer.status.value,
                failure_code=transfer.failure_code,
            ),
        )


def vars_of(report: ReconcileReport) -> dict[str, int]:
    return {
        "examined": report.examined,
        "confirmed": report.confirmed,
        "failed": report.failed,
        "still_pending": report.still_pending,
        "resubmitted": report.resubmitted,
    }
