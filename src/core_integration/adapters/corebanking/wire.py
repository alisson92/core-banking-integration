"""The core's wire format, exactly as the core sends it (legacy style on purpose).

These models VALIDATE what comes from the core. If the core changes its payload,
we fail loudly here instead of corrupting our domain.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Wire(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class AccountWire(_Wire):
    acct_no: str = Field(alias="ACCT_NO")
    cust_nm: str = Field(alias="CUST_NM")
    ccy_cd: str = Field(alias="CCY_CD")
    status_cd: Literal["A", "B", "C"] = Field(alias="STATUS_CD")


class BalanceWire(_Wire):
    acct_no: str = Field(alias="ACCT_NO")
    avail_bal: Decimal = Field(alias="AVAIL_BAL")
    ledger_bal: Decimal = Field(alias="LEDGER_BAL")
    ccy_cd: str = Field(alias="CCY_CD")


class TransactionWire(_Wire):
    txn_id: str = Field(alias="TXN_ID")
    acct_no: str = Field(alias="ACCT_NO")
    dr_cr: Literal["D", "C"] = Field(alias="DR_CR")
    amt: Decimal = Field(alias="AMT")
    ccy_cd: str = Field(alias="CCY_CD")
    post_dt: str = Field(alias="POST_DT", pattern=r"^\d{8}$")
    narr: str = Field(default="", alias="NARR")


class StatementWire(_Wire):
    acct_no: str = Field(alias="ACCT_NO")
    txns: list[TransactionWire] = Field(alias="TXNS")


class TransferResultWire(_Wire):
    ref_id: str = Field(alias="REF_ID")
    txn_id: str | None = Field(default=None, alias="TXN_ID")
    status_cd: Literal["C", "P", "R"] = Field(
        alias="STATUS_CD"
    )  # confirmed / processing / rejected
    err_cd: str | None = Field(default=None, alias="ERR_CD")
    err_msg: str | None = Field(default=None, alias="ERR_MSG")


class ErrorWire(_Wire):
    err_cd: str = Field(alias="ERR_CD")
    err_msg: str = Field(default="", alias="ERR_MSG")
