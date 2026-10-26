"""In-memory transfer repository.

Good enough to learn with. NOT good enough for production: data is lost on restart and it
cannot be shared between replicas. The Helm chart therefore runs a single replica until
Phase 3 replaces this with PostgreSQL (see docs/roadmap.md).

It returns COPIES, like a real database would. Mutating an object you got back does nothing
until you call `update`.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from core_integration.domain.models import Transfer, TransferStatus


class InMemoryTransferRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, Transfer] = {}
        self._id_by_key: dict[str, str] = {}

    async def add(self, transfer: Transfer) -> None:
        if transfer.idempotency_key in self._id_by_key:
            raise ValueError("duplicate idempotency key")  # a UNIQUE constraint in a real DB
        self._by_id[transfer.id] = replace(transfer)
        self._id_by_key[transfer.idempotency_key] = transfer.id

    async def update(self, transfer: Transfer) -> None:
        self._by_id[transfer.id] = replace(transfer)

    async def get(self, transfer_id: str) -> Transfer | None:
        found = self._by_id.get(transfer_id)
        return replace(found) if found else None

    async def get_by_idempotency_key(self, key: str) -> Transfer | None:
        transfer_id = self._id_by_key.get(key)
        return await self.get(transfer_id) if transfer_id else None

    async def list_pending(self, created_before: datetime) -> list[Transfer]:
        return [
            replace(t)
            for t in self._by_id.values()
            if t.status is TransferStatus.PENDING and t.created_at <= created_before
        ]
