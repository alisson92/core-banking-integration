"""Two contracts are checked here:

1. Our public API contract (api/openapi.yaml) vs the running app.
2. The core's wire format (adapter models) vs what the mock core really answers.
   With a real core, this second test would run against its sandbox.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml
from core_banking_mock.main import create_app as create_core_app

from core_integration.adapters.corebanking.wire import (
    AccountWire,
    BalanceWire,
    ErrorWire,
    StatementWire,
    TransferResultWire,
)
from core_integration.api.app import create_app
from tests.conftest import CORE_KEY, JOAO, MARIA, make_settings

CONTRACT = Path(__file__).resolve().parents[2] / "api" / "openapi.yaml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def operations(spec: dict) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, item in spec["paths"].items()
        for method in item
        if method in HTTP_METHODS
    }


def test_running_app_implements_every_operation_in_the_contract():
    contract = yaml.safe_load(CONTRACT.read_text())
    app = create_app(make_settings())
    implemented = operations(app.openapi())
    missing = operations(contract) - implemented
    assert not missing, f"in the contract but not implemented: {sorted(missing)}"


def test_running_app_has_no_undocumented_business_operations():
    contract = yaml.safe_load(CONTRACT.read_text())
    app = create_app(make_settings())
    # /metrics is operational and intentionally not part of the business contract.
    extra = {op for op in operations(app.openapi()) - operations(contract) if op[1] != "/metrics"}
    assert not extra, f"implemented but not in the contract: {sorted(extra)}"


def test_contract_operation_ids_are_unique():
    contract = yaml.safe_load(CONTRACT.read_text())
    ids = [
        op["operationId"]
        for item in contract["paths"].values()
        for method, op in item.items()
        if method in HTTP_METHODS
    ]
    assert len(ids) == len(set(ids))


@pytest.fixture
async def core():
    app = create_core_app(api_key=CORE_KEY)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://core.test",
        headers={"X-API-Key": CORE_KEY},
    ) as client:
        yield client


async def test_mock_core_answers_match_the_adapter_wire_models(core: httpx.AsyncClient):
    AccountWire.model_validate((await core.get(f"/core/v1/accounts/{MARIA}")).json())
    BalanceWire.model_validate((await core.get(f"/core/v1/accounts/{MARIA}/balance")).json())
    statement = await core.get(
        f"/core/v1/accounts/{MARIA}/transactions",
        params={"FROM_DT": "20260101", "TO_DT": "20261231"},
    )
    assert len(StatementWire.model_validate(statement.json()).txns) == 3

    body = {
        "REF_ID": "CONTRACT0001",
        "FROM_ACCT": MARIA,
        "TO_ACCT": JOAO,
        "AMT": "1.00",
        "CCY_CD": "BRL",
    }
    created = await core.post("/core/v1/transfers", json=body)
    assert TransferResultWire.model_validate(created.json()).status_cd == "C"
    found = await core.get("/core/v1/transfers/CONTRACT0001")
    assert TransferResultWire.model_validate(found.json()).ref_id == "CONTRACT0001"


async def test_mock_core_errors_match_the_error_model(core: httpx.AsyncClient):
    duplicate_body = {
        "REF_ID": "CONTRACT0002",
        "FROM_ACCT": MARIA,
        "TO_ACCT": JOAO,
        "AMT": "1.00",
        "CCY_CD": "BRL",
    }
    await core.post("/core/v1/transfers", json=duplicate_body)
    for response, code in [
        (await core.get("/core/v1/accounts/9999999999"), "ACCT_NOT_FOUND"),
        (await core.get("/core/v1/transfers/NOPE"), "REF_NOT_FOUND"),
        (await core.post("/core/v1/transfers", json=duplicate_body), "DUPLICATE_REF"),
    ]:
        assert ErrorWire.model_validate(response.json()).err_cd == code


async def test_mock_core_admin_can_inject_and_clear_faults(core: httpx.AsyncClient):
    set_response = await core.post("/admin/faults", json={"fail_next": 1})
    assert set_response.json()["fail_next"] == 1
    assert (await core.get(f"/core/v1/accounts/{MARIA}")).status_code == 503
    assert (await core.get(f"/core/v1/accounts/{MARIA}")).status_code == 200
    cleared = await core.delete("/admin/faults")
    assert cleared.json()["fail_next"] == 0
