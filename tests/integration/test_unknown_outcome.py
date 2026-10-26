"""The scary cases: we sent a transfer and do NOT know what happened.

These tests are the reason idempotency keys, core references and reconciliation exist.
"""

from tests.conftest import JOAO, MARIA, Harness


async def test_timeout_after_commit_is_resolved_by_retry_through_duplicate_reference(
    core_app, api: Harness
):
    # Attempt 1: the core COMMITS, then answers too slowly. We time out.
    # Attempt 2: same reference -> the core says DUPLICATE_REF -> we fetch the original result.
    core_app.state.faults.slow_after_commit_ms = 500
    core_app.state.faults.slow_after_commit_next = 1

    response = await api.transfer("unk-1", amount="100.00")

    assert response.status_code == 201
    assert response.json()["status"] == "CONFIRMED"
    assert await api.balance(MARIA) == "4900.00"  # debited exactly once, despite two attempts


async def test_unknown_outcome_stays_pending_then_reconciliation_confirms_it(core_app, make_api):
    api = await make_api(write_max_attempts=1)  # no retry: we really stay in the dark
    core_app.state.faults.slow_after_commit_ms = 500
    core_app.state.faults.slow_after_commit_next = 1

    response = await api.transfer("unk-2", amount="100.00")
    assert response.status_code == 202
    transfer_id = response.json()["id"]
    assert response.json()["status"] == "PENDING"

    # The money DID move, even though we answered PENDING. That is the whole point.
    assert await api.balance(MARIA) == "4900.00"

    report = (await api.client.post("/internal/reconcile")).json()
    assert report == {
        "examined": 1,
        "confirmed": 1,
        "failed": 0,
        "still_pending": 0,
        "resubmitted": 0,
    }
    fetched = (await api.client.get(f"/v1/transfers/{transfer_id}")).json()
    assert fetched["status"] == "CONFIRMED"
    assert await api.balance(MARIA) == "4900.00"  # reconciliation did not move money again


async def test_reconciliation_resubmits_when_the_core_never_saw_the_request(core_app, make_api):
    api = await make_api(write_max_attempts=1)
    core_app.state.faults.fail_next = 1  # the core rejects the call BEFORE applying anything

    response = await api.transfer("unk-3", amount="100.00")
    assert response.status_code == 202
    assert await api.balance(MARIA) == "5000.00"  # nothing moved

    report = (await api.client.post("/internal/reconcile")).json()
    assert report["resubmitted"] == 1
    assert report["confirmed"] == 1
    assert await api.balance(MARIA) == "4900.00"
    assert await api.balance(JOAO) == "1100.00"


async def test_reconciliation_leaves_transfers_pending_while_the_core_is_down(core_app, make_api):
    api = await make_api(write_max_attempts=1, read_max_attempts=1, breaker_failure_threshold=50)
    core_app.state.faults.fail_next = 1
    created = await api.transfer("unk-4")
    assert created.status_code == 202

    core_app.state.faults.fail_next = 5  # the core is still down during reconciliation
    report = (await api.client.post("/internal/reconcile")).json()
    assert report["still_pending"] == 1
    assert report["confirmed"] == 0

    core_app.state.faults.fail_next = 0  # the core is back
    report = (await api.client.post("/internal/reconcile")).json()
    assert report["confirmed"] == 1


async def test_reconciliation_marks_failed_when_the_core_refuses_the_resubmission(
    core_app, make_api
):
    api = await make_api(write_max_attempts=1)
    core_app.state.faults.fail_next = 1
    created = (await api.transfer("unk-5", amount="100.00")).json()
    assert created["status"] == "PENDING"

    # Meanwhile the account is drained, so the resubmission will be refused.
    core_app.state.store.get_account(MARIA).balance = 0

    report = (await api.client.post("/internal/reconcile")).json()
    assert report["failed"] == 1
    fetched = (await api.client.get(f"/v1/transfers/{created['id']}")).json()
    assert (fetched["status"], fetched["failure_code"]) == ("FAILED", "INSUFFICIENT_FUNDS")


async def test_reconcile_with_nothing_pending_is_a_no_op(api: Harness):
    report = (await api.client.post("/internal/reconcile")).json()
    assert report["examined"] == 0
