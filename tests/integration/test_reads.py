"""Walking skeleton: read-only operations, end to end (HTTP -> use case -> adapter -> mock core)."""

from tests.conftest import MARIA, Harness


async def test_get_balance(api: Harness):
    response = await api.client.get(f"/v1/accounts/{MARIA}/balance")
    assert response.status_code == 200
    body = response.json()
    assert body["account_id"] == MARIA
    assert body["available"] == {"amount": "5000.00", "currency": "BRL"}
    assert response.headers["x-request-id"]


async def test_unknown_account_is_404_problem_details(api: Harness):
    response = await api.client.get("/v1/accounts/9999999999/balance")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "ACCOUNT_NOT_FOUND"


async def test_malformed_account_id_is_rejected_before_reaching_the_core(api: Harness):
    response = await api.client.get("/v1/accounts/abc/balance")
    assert response.status_code == 422


async def test_statement_returns_transactions_in_the_period(api: Harness):
    response = await api.client.get(
        f"/v1/accounts/{MARIA}/statement", params={"from": "2026-10-01", "to": "2026-10-31"}
    )
    assert response.status_code == 200
    transactions = response.json()["transactions"]
    assert [t["description"] for t in transactions] == ["SALARY", "RENT"]
    assert [t["kind"] for t in transactions] == ["CREDIT", "DEBIT"]
    assert transactions[0]["booked_on"] == "2026-10-05"


async def test_statement_rejects_inverted_period(api: Harness):
    response = await api.client.get(
        f"/v1/accounts/{MARIA}/statement", params={"from": "2026-10-31", "to": "2026-10-01"}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_PERIOD"


async def test_statement_rejects_periods_longer_than_92_days(api: Harness):
    response = await api.client.get(
        f"/v1/accounts/{MARIA}/statement", params={"from": "2026-01-01", "to": "2026-12-31"}
    )
    assert response.status_code == 400
    assert response.json()["code"] == "PERIOD_TOO_LONG"
