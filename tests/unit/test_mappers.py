from decimal import Decimal

import pytest

from core_integration.adapters.corebanking import mappers
from core_integration.adapters.corebanking.wire import (
    AccountWire,
    BalanceWire,
    TransactionWire,
    TransferResultWire,
)
from core_integration.domain.errors import (
    AccountNotAvailable,
    AccountNotFound,
    BusinessRuleViolation,
    InsufficientFunds,
)
from core_integration.domain.models import AccountStatus, TransactionKind, TransferStatus


def test_account_status_letters_become_an_enum():
    wire = AccountWire.model_validate(
        {"ACCT_NO": "0001234567", "CUST_NM": "MARIA", "CCY_CD": "BRL", "STATUS_CD": "B"}
    )
    account = mappers.account_from_wire(wire)
    assert account.status is AccountStatus.BLOCKED
    assert account.holder_name == "MARIA"


def test_balance_becomes_money():
    wire = BalanceWire.model_validate(
        {"ACCT_NO": "1", "AVAIL_BAL": "10.50", "LEDGER_BAL": "12.00", "CCY_CD": "BRL"}
    )
    balance = mappers.balance_from_wire(wire)
    assert balance.available.amount == Decimal("10.50")
    assert balance.ledger.amount == Decimal("12.00")


def test_transaction_dates_and_direction():
    wire = TransactionWire.model_validate(
        {
            "TXN_ID": "TX1",
            "ACCT_NO": "1",
            "DR_CR": "D",
            "AMT": "5.00",
            "CCY_CD": "BRL",
            "POST_DT": "20261010",
            "NARR": "RENT",
        }
    )
    txn = mappers.transaction_from_wire(wire)
    assert txn.kind is TransactionKind.DEBIT
    assert txn.booked_on.isoformat() == "2026-10-10"


@pytest.mark.parametrize(
    ("status_cd", "expected"),
    [("C", TransferStatus.CONFIRMED), ("P", TransferStatus.PENDING), ("R", TransferStatus.FAILED)],
)
def test_transfer_status_letters(status_cd: str, expected: TransferStatus):
    wire = TransferResultWire.model_validate(
        {"REF_ID": "R1", "TXN_ID": "TX1", "STATUS_CD": status_cd, "ERR_CD": "INSUFF_FUNDS"}
    )
    result = mappers.transfer_result_from_wire(wire)
    assert result.status is expected
    if expected is TransferStatus.FAILED:
        assert result.failure_code == "INSUFFICIENT_FUNDS"


def test_rejected_with_unknown_error_code_keeps_the_core_code():
    wire = TransferResultWire.model_validate(
        {"REF_ID": "R1", "STATUS_CD": "R", "ERR_CD": "WEIRD", "ERR_MSG": "strange"}
    )
    assert mappers.transfer_result_from_wire(wire).failure_code == "WEIRD"


@pytest.mark.parametrize(
    ("code", "expected_type", "expected_code"),
    [
        ("ACCT_NOT_FOUND", AccountNotFound, "ACCOUNT_NOT_FOUND"),
        ("ACCT_BLOCKED", AccountNotAvailable, "ACCOUNT_BLOCKED"),
        ("ACCT_CLOSED", AccountNotAvailable, "ACCOUNT_CLOSED"),
        ("INSUFF_FUNDS", InsufficientFunds, "INSUFFICIENT_FUNDS"),
        ("CCY_MISMATCH", BusinessRuleViolation, "CURRENCY_MISMATCH"),
    ],
)
def test_error_codes_map_to_domain_errors(code, expected_type, expected_code):
    error = mappers.error_from_code(code, "msg")
    assert isinstance(error, expected_type)
    assert error.code == expected_code


def test_unknown_error_code_is_not_guessed():
    assert mappers.error_from_code("SOMETHING_NEW", "msg") is None
    assert mappers.error_from_code(None, "msg") is None
