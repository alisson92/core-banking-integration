"""Transfers: the happy path, idempotency, and business refusals."""

import asyncio

from tests.conftest import BLOCKED, CLOSED, JOAO, MARIA, Harness


async def test_transfer_is_confirmed_and_moves_money(api: Harness):
    response = await api.transfer("key-1", amount="100.00")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "CONFIRMED"
    assert response.headers["location"] == f"/v1/transfers/{body['id']}"
    assert await api.balance(MARIA) == "4900.00"
    assert await api.balance(JOAO) == "1100.00"


async def test_get_transfer_returns_the_same_state(api: Harness):
    created = (await api.transfer("key-2")).json()
    fetched = await api.client.get(f"/v1/transfers/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "CONFIRMED"


async def test_unknown_transfer_is_404(api: Harness):
    response = await api.client.get("/v1/transfers/does-not-exist")
    assert response.status_code == 404
    assert response.json()["code"] == "TRANSFER_NOT_FOUND"


async def test_replay_with_same_key_returns_same_transfer_and_moves_money_once(api: Harness):
    first = await api.transfer("key-3")
    second = await api.transfer("key-3")
    assert second.status_code == 200
    assert second.headers["idempotent-replayed"] == "true"
    assert second.json()["id"] == first.json()["id"]
    assert await api.balance(MARIA) == "4900.00"  # debited ONCE


async def test_same_key_with_a_different_body_is_refused(api: Harness):
    await api.transfer("key-4", amount="100.00")
    response = await api.transfer("key-4", amount="999.00")
    assert response.status_code == 422
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert await api.balance(MARIA) == "4900.00"


async def test_concurrent_requests_with_the_same_key_create_one_transfer(api: Harness):
    responses = await asyncio.gather(*[api.transfer("key-5") for _ in range(5)])
    assert {r.json()["id"] for r in responses} == {responses[0].json()["id"]}
    assert sum(r.status_code == 201 for r in responses) == 1
    assert await api.balance(MARIA) == "4900.00"


async def test_missing_idempotency_key_is_a_400(api: Harness):
    response = await api.client.post(
        "/v1/transfers",
        json={"source_account": MARIA, "destination_account": JOAO, "amount": "1.00"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "MISSING_IDEMPOTENCY_KEY"


async def test_insufficient_funds_fails_without_moving_money(api: Harness):
    response = await api.transfer("key-6", amount="9999.00")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["failure_code"] == "INSUFFICIENT_FUNDS"
    assert await api.balance(MARIA) == "5000.00"


async def test_blocked_and_closed_accounts_fail(api: Harness):
    blocked = (await api.transfer("key-7", destination=BLOCKED)).json()
    closed = (await api.transfer("key-8", destination=CLOSED)).json()
    assert (blocked["status"], blocked["failure_code"]) == ("FAILED", "ACCOUNT_BLOCKED")
    assert (closed["status"], closed["failure_code"]) == ("FAILED", "ACCOUNT_CLOSED")


async def test_unknown_destination_fails(api: Harness):
    body = (await api.transfer("key-9", destination="0000000001")).json()
    assert (body["status"], body["failure_code"]) == ("FAILED", "ACCOUNT_NOT_FOUND")


async def test_invalid_input_is_rejected(api: Harness):
    zero = await api.transfer("key-10", amount="0.00")
    same = await api.transfer("key-11", destination=MARIA)
    too_precise = await api.transfer("key-12", amount="1.001")
    assert zero.status_code == 422
    assert same.status_code == 400
    assert same.json()["code"] == "SAME_ACCOUNT"
    assert too_precise.status_code == 422
