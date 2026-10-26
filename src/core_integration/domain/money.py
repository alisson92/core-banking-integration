"""Money value object.

Rule number one of financial code: never use float for money.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_CURRENCY = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str = "BRL"

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("amount must be a Decimal (never use float for money)")
        if not self.amount.is_finite():
            raise ValueError("amount must be finite")
        exponent = self.amount.as_tuple().exponent
        if isinstance(exponent, int) and exponent < -2:
            raise ValueError("amount must have at most 2 decimal places")
        if not _CURRENCY.match(self.currency):
            raise ValueError("currency must be a 3-letter ISO 4217 code")

    @classmethod
    def parse(cls, value: str, currency: str = "BRL") -> Money:
        try:
            return cls(Decimal(value), currency)
        except InvalidOperation as exc:
            raise ValueError(f"invalid money amount: {value!r}") from exc

    def is_positive(self) -> bool:
        return self.amount > 0

    def to_wire(self) -> str:
        """Fixed 2-decimal string, e.g. '100.00'. Safe to send as JSON."""
        return f"{self.amount:.2f}"
