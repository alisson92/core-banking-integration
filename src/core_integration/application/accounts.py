"""Read-only use cases: balance and statement."""

from __future__ import annotations

from datetime import date

from core_integration.application.ports import CoreBankingGateway
from core_integration.domain.errors import InvalidRequest
from core_integration.domain.models import Balance, Transaction

MAX_STATEMENT_DAYS = 92  # protects the core from huge queries


class AccountService:
    def __init__(self, gateway: CoreBankingGateway) -> None:
        self._gateway = gateway

    async def get_balance(self, account_id: str) -> Balance:
        return await self._gateway.get_balance(account_id)

    async def get_statement(self, account_id: str, start: date, end: date) -> list[Transaction]:
        if start > end:
            raise InvalidRequest("'from' must not be after 'to'", code="INVALID_PERIOD")
        if (end - start).days > MAX_STATEMENT_DAYS:
            raise InvalidRequest(
                f"period is too long (maximum {MAX_STATEMENT_DAYS} days)", code="PERIOD_TOO_LONG"
            )
        return await self._gateway.get_statement(account_id, start, end)
