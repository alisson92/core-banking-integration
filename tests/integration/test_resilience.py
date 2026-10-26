"""What happens when the core misbehaves: retries, timeouts, circuit breaker."""

from tests.conftest import MARIA, Harness


async def test_read_retries_through_transient_failures(core_app, api: Harness):
    core_app.state.faults.fail_next = 2  # attempts 1 and 2 fail, attempt 3 works
    response = await api.client.get(f"/v1/accounts/{MARIA}/balance")
    assert response.status_code == 200
    assert core_app.state.faults.fail_next == 0


async def test_read_gives_up_after_max_attempts_with_503_and_retry_after(core_app, api: Harness):
    core_app.state.faults.fail_next = 10
    response = await api.client.get(f"/v1/accounts/{MARIA}/balance")
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert response.json()["code"] in {"CORE_UNAVAILABLE", "CIRCUIT_OPEN"}


async def test_slow_core_hits_our_timeout(core_app, api: Harness):
    core_app.state.faults.latency_ms = 500  # our timeout is 200 ms
    response = await api.client.get(f"/v1/accounts/{MARIA}/balance")
    assert response.status_code == 503


async def test_circuit_opens_and_protects_the_core(core_app, api: Harness):
    core_app.state.faults.fail_next = 10
    await api.client.get(f"/v1/accounts/{MARIA}/balance")  # 3 failures -> opens (threshold 3)
    consumed = 10 - core_app.state.faults.fail_next
    assert consumed == 3

    response = await api.client.get(f"/v1/accounts/{MARIA}/balance")
    assert response.status_code == 503
    assert response.json()["code"] == "CIRCUIT_OPEN"
    assert core_app.state.faults.fail_next == 10 - consumed  # the core was NOT called again

    ready = await api.client.get("/health/ready")
    assert ready.status_code == 200  # readiness does not depend on the core
    assert ready.json()["core_circuit"] == "open"


async def test_circuit_recovers_after_the_recovery_timeout(core_app, api: Harness):
    core_app.state.faults.fail_next = 3
    await api.client.get(f"/v1/accounts/{MARIA}/balance")  # opens the circuit
    assert (await api.client.get("/health/ready")).json()["core_circuit"] == "open"

    api.clock.advance(31)  # recovery timeout is 30 s
    assert (await api.client.get("/health/ready")).json()["core_circuit"] == "half_open"

    response = await api.client.get(f"/v1/accounts/{MARIA}/balance")  # the trial call succeeds
    assert response.status_code == 200
    assert (await api.client.get("/health/ready")).json()["core_circuit"] == "closed"


async def test_business_errors_do_not_trip_the_circuit(api: Harness):
    for _ in range(10):
        response = await api.client.get("/v1/accounts/9999999999/balance")
        assert response.status_code == 404
    assert (await api.client.get("/health/ready")).json()["core_circuit"] == "closed"
