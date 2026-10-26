from decimal import Decimal

import pytest

from core_integration.domain.money import Money


def test_to_wire_always_has_two_decimals():
    assert Money(Decimal("100")).to_wire() == "100.00"
    assert Money(Decimal("0.5")).to_wire() == "0.50"


def test_rejects_float():
    with pytest.raises(TypeError):
        Money(100.10)  # type: ignore[arg-type]


def test_rejects_more_than_two_decimal_places():
    with pytest.raises(ValueError, match="2 decimal places"):
        Money(Decimal("1.001"))


def test_rejects_bad_currency():
    with pytest.raises(ValueError, match="currency"):
        Money(Decimal("1.00"), "reais")


def test_rejects_non_finite():
    with pytest.raises(ValueError, match="finite"):
        Money(Decimal("NaN"))


def test_parse_valid_and_invalid():
    assert Money.parse("10.25").amount == Decimal("10.25")
    with pytest.raises(ValueError, match="invalid money amount"):
        Money.parse("ten")


def test_is_positive():
    assert Money(Decimal("0.01")).is_positive()
    assert not Money(Decimal("0.00")).is_positive()
    assert not Money(Decimal("-1.00")).is_positive()
