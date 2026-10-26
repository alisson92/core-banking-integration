"""In-memory ledger that imitates a legacy core banking system.

Business rules live here (balances, blocked accounts, duplicate references).
The HTTP layer in `main.py` only translates them to and from JSON.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

# Legacy constraint: the reference is at most 20 letters or digits.
_REF_PATTERN = re.compile(r"^[A-Za-z0-9]{1,20}$")


class CoreError(Exception):
    """A business or protocol error, already shaped like the core's error body."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass
class AccountRecord:
    acct_no: str
    cust_nm: str
    ccy_cd: str
    status_cd: str  # A = active, B = blocked, C = closed
    balance: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class EntryRecord:
    txn_id: str
    acct_no: str
    dr_cr: str  # D = debit, C = credit
    amt: Decimal
    ccy_cd: str
    post_dt: str  # YYYYMMDD
    narr: str
    ref_id: str | None = None


@dataclass(frozen=True)
class TransferRecord:
    ref_id: str
    txn_id: str
    from_acct: str
    to_acct: str
    amt: Decimal
    ccy_cd: str
    status_cd: str = "C"  # C = confirmed


class CoreStore:
    def __init__(self, today: Callable[[], date] = date.today) -> None:
        self._today = today
        self.reset()

    # ------------------------------------------------------------------ setup
    def reset(self) -> None:
        self._accounts: dict[str, AccountRecord] = {
            "0001234567": AccountRecord("0001234567", "MARIA SILVA", "BRL", "A"),
            "0007654321": AccountRecord("0007654321", "JOAO SOUZA", "BRL", "A"),
            "0009999999": AccountRecord("0009999999", "CONTA BLOQUEADA", "BRL", "B"),
            "0008888888": AccountRecord("0008888888", "CONTA ENCERRADA", "BRL", "C"),
        }
        self._entries: list[EntryRecord] = []
        self._transfers: dict[str, TransferRecord] = {}
        self._txn_counter = 0
        self._seed()

    def _seed(self) -> None:
        self._post("0001234567", "C", Decimal("4000.00"), "20260901", "OPENING")
        self._post("0001234567", "C", Decimal("2500.00"), "20261005", "SALARY")
        self._post("0001234567", "D", Decimal("1500.00"), "20261010", "RENT")
        self._post("0007654321", "C", Decimal("1000.00"), "20260915", "OPENING")
        self._post("0009999999", "C", Decimal("200.00"), "20260920", "OPENING")

    # ---------------------------------------------------------------- queries
    def get_account(self, acct_no: str) -> AccountRecord:
        account = self._accounts.get(acct_no)
        if account is None:
            raise CoreError(404, "ACCT_NOT_FOUND", f"account {acct_no} not found")
        return account

    def entries_between(self, acct_no: str, from_dt: str, to_dt: str) -> list[EntryRecord]:
        self.get_account(acct_no)
        return [e for e in self._entries if e.acct_no == acct_no and from_dt <= e.post_dt <= to_dt]

    def get_transfer(self, ref_id: str) -> TransferRecord:
        record = self._transfers.get(ref_id)
        if record is None:
            raise CoreError(404, "REF_NOT_FOUND", f"reference {ref_id} not found")
        return record

    # --------------------------------------------------------------- commands
    def transfer(
        self, ref_id: str, from_acct: str, to_acct: str, amt: Decimal, ccy_cd: str
    ) -> TransferRecord:
        """Apply a transfer atomically. No `await` happens here, so it cannot interleave."""
        if not _REF_PATTERN.match(ref_id):
            raise CoreError(400, "BAD_REF_ID", "REF_ID must have 1-20 letters or digits")
        if ref_id in self._transfers:
            raise CoreError(409, "DUPLICATE_REF", f"reference {ref_id} was already processed")
        if amt <= 0:
            raise CoreError(422, "INVALID_AMT", "amount must be greater than zero")
        if from_acct == to_acct:
            raise CoreError(422, "SAME_ACCOUNT", "source and destination must differ")

        source = self._account_for_transfer(from_acct)
        destination = self._account_for_transfer(to_acct)
        if source.ccy_cd != ccy_cd or destination.ccy_cd != ccy_cd:
            raise CoreError(422, "CCY_MISMATCH", "currency does not match the accounts")
        if source.balance < amt:
            raise CoreError(422, "INSUFF_FUNDS", "insufficient funds")

        txn_id = self._next_txn_id()
        post_dt = self._today().strftime("%Y%m%d")
        self._post(from_acct, "D", amt, post_dt, f"TRF TO {to_acct}", ref_id, txn_id)
        self._post(to_acct, "C", amt, post_dt, f"TRF FROM {from_acct}", ref_id, txn_id)
        record = TransferRecord(ref_id, txn_id, from_acct, to_acct, amt, ccy_cd)
        self._transfers[ref_id] = record
        return record

    # --------------------------------------------------------------- internals
    def _account_for_transfer(self, acct_no: str) -> AccountRecord:
        account = self._accounts.get(acct_no)
        if account is None:
            raise CoreError(422, "ACCT_NOT_FOUND", f"account {acct_no} not found")
        if account.status_cd == "B":
            raise CoreError(422, "ACCT_BLOCKED", f"account {acct_no} is blocked")
        if account.status_cd == "C":
            raise CoreError(422, "ACCT_CLOSED", f"account {acct_no} is closed")
        return account

    def _next_txn_id(self) -> str:
        self._txn_counter += 1
        return f"TX{self._txn_counter:09d}"

    def _post(
        self,
        acct_no: str,
        dr_cr: str,
        amt: Decimal,
        post_dt: str,
        narr: str,
        ref_id: str | None = None,
        txn_id: str | None = None,
    ) -> None:
        account = self._accounts[acct_no]
        account.balance += amt if dr_cr == "C" else -amt
        self._entries.append(
            EntryRecord(
                txn_id=txn_id or self._next_txn_id(),
                acct_no=acct_no,
                dr_cr=dr_cr,
                amt=amt,
                ccy_cd=account.ccy_cd,
                post_dt=post_dt,
                narr=narr,
                ref_id=ref_id,
            )
        )
