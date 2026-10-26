from decimal import Decimal

import pytest

from core_integration.domain.errors import InvalidTransition
from core_integration.domain.models import Transfer, TransferStatus
from core_integration.domain.money import Money


def new_transfer() -> Transfer:
    return Transfer.new(
        idempotency_key="k1",
        request_hash="h",
        source_account="0001234567",
        destination_account="0007654321",
        amount=Money(Decimal("10.00")),
    )


def test_starts_pending():
    assert new_transfer().status is TransferStatus.PENDING


def test_core_reference_respects_legacy_limit():
    transfer = new_transfer()
    assert len(transfer.core_reference) == 20
    assert transfer.core_reference.isalnum()


def test_confirm():
    transfer = new_transfer()
    transfer.confirm("TX1")
    assert transfer.status is TransferStatus.CONFIRMED
    assert transfer.core_transaction_id == "TX1"


def test_fail():
    transfer = new_transfer()
    transfer.fail("INSUFFICIENT_FUNDS", "no money")
    assert transfer.status is TransferStatus.FAILED
    assert transfer.failure_code == "INSUFFICIENT_FUNDS"


@pytest.mark.parametrize("first", ["confirm", "fail"])
@pytest.mark.parametrize("second", ["confirm", "fail"])
def test_final_states_never_change(first: str, second: str):
    transfer = new_transfer()
    _apply(transfer, first)
    with pytest.raises(InvalidTransition):
        _apply(transfer, second)


def _apply(transfer: Transfer, action: str) -> None:
    if action == "confirm":
        transfer.confirm("TX1")
    else:
        transfer.fail("CODE", "reason")
