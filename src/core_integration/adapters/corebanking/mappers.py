"""Translate between the core's wire format and our domain model (both directions of meaning)."""

from __future__ import annotations

from datetime import datetime

from core_integration.adapters.corebanking.wire import (
    AccountWire,
    BalanceWire,
    TransactionWire,
    TransferResultWire,
)
from core_integration.application.ports import CoreTransferResult
from core_integration.domain.errors import (
    AccountNotAvailable,
    AccountNotFound,
    BusinessRuleViolation,
    DomainError,
    InsufficientFunds,
)
from core_integration.domain.models import (
    Account,
    AccountStatus,
    Balance,
    Transaction,
    TransactionKind,
    TransferStatus,
)
from core_integration.domain.money import Money

_ACCOUNT_STATUS = {
    "A": AccountStatus.ACTIVE,
    "B": AccountStatus.BLOCKED,
    "C": AccountStatus.CLOSED,
}

_TRANSFER_STATUS = {
    "C": TransferStatus.CONFIRMED,
    "P": TransferStatus.PENDING,
    "R": TransferStatus.FAILED,
}

# Core error code -> our code, for rules that are plain business refusals.
_BUSINESS_CODES = {
    "SAME_ACCOUNT": "SAME_ACCOUNT",
    "INVALID_AMT": "INVALID_AMOUNT",
    "CCY_MISMATCH": "CURRENCY_MISMATCH",
}


def account_from_wire(w: AccountWire) -> Account:
    return Account(
        id=w.acct_no,
        holder_name=w.cust_nm,
        currency=w.ccy_cd,
        status=_ACCOUNT_STATUS[w.status_cd],
    )


def balance_from_wire(w: BalanceWire) -> Balance:
    return Balance(
        account_id=w.acct_no,
        available=Money(w.avail_bal, w.ccy_cd),
        ledger=Money(w.ledger_bal, w.ccy_cd),
    )


def transaction_from_wire(w: TransactionWire) -> Transaction:
    return Transaction(
        id=w.txn_id,
        account_id=w.acct_no,
        kind=TransactionKind.CREDIT if w.dr_cr == "C" else TransactionKind.DEBIT,
        amount=Money(w.amt, w.ccy_cd),
        booked_on=datetime.strptime(w.post_dt, "%Y%m%d").date(),
        description=w.narr,
    )


def transfer_result_from_wire(w: TransferResultWire) -> CoreTransferResult:
    status = _TRANSFER_STATUS[w.status_cd]
    failure_code = None
    failure_reason = None
    if status is TransferStatus.FAILED:
        mapped = error_from_code(w.err_cd, w.err_msg or "")
        failure_code = mapped.code if mapped else (w.err_cd or "CORE_REJECTED")
        failure_reason = w.err_msg or "rejected by the core"
    return CoreTransferResult(
        reference=w.ref_id,
        status=status,
        core_transaction_id=w.txn_id,
        failure_code=failure_code,
        failure_reason=failure_reason,
    )


def error_from_code(code: str | None, message: str) -> DomainError | None:
    """Map a core error code to a domain error. None means: we do not know this code."""
    if code == "ACCT_NOT_FOUND":
        return AccountNotFound(message)
    if code == "ACCT_BLOCKED":
        return AccountNotAvailable(message, code="ACCOUNT_BLOCKED")
    if code == "ACCT_CLOSED":
        return AccountNotAvailable(message, code="ACCOUNT_CLOSED")
    if code == "INSUFF_FUNDS":
        return InsufficientFunds(message)
    if code in _BUSINESS_CODES:
        return BusinessRuleViolation(message, code=_BUSINESS_CODES[code])
    return None
