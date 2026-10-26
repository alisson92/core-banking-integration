import pytest

from core_integration.domain.errors import CircuitOpen
from core_integration.infrastructure.resilience import CircuitBreaker, CircuitState, RetryPolicy


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make(threshold: int = 3, recovery: float = 30.0):
    clock = Clock()
    changes: list[CircuitState] = []
    breaker = CircuitBreaker(
        failure_threshold=threshold,
        recovery_timeout=recovery,
        clock=clock,
        on_state_change=changes.append,
    )
    return breaker, clock, changes


def fail(breaker: CircuitBreaker, times: int) -> None:
    for _ in range(times):
        breaker.before_call()
        breaker.record_failure()


def test_opens_after_threshold_and_refuses_calls():
    breaker, _, changes = make()
    fail(breaker, 3)
    assert breaker.state is CircuitState.OPEN
    assert changes == [CircuitState.OPEN]
    with pytest.raises(CircuitOpen):
        breaker.before_call()


def test_success_resets_the_failure_count():
    breaker, _, _ = make()
    fail(breaker, 2)
    breaker.before_call()
    breaker.record_success()
    fail(breaker, 2)  # 2 again, not 4: still closed
    assert breaker.state is CircuitState.CLOSED


def test_becomes_half_open_after_recovery_timeout():
    breaker, clock, _ = make()
    fail(breaker, 3)
    clock.now = 29.9
    assert breaker.state is CircuitState.OPEN
    clock.now = 30.0
    assert breaker.state is CircuitState.HALF_OPEN


def test_half_open_allows_a_single_trial_call():
    breaker, clock, _ = make()
    fail(breaker, 3)
    clock.now = 30.0
    breaker.before_call()  # the trial
    with pytest.raises(CircuitOpen):
        breaker.before_call()  # a second one is refused


def test_trial_success_closes_the_circuit():
    breaker, clock, changes = make()
    fail(breaker, 3)
    clock.now = 30.0
    breaker.before_call()
    breaker.record_success()
    assert breaker.state is CircuitState.CLOSED
    assert changes == [CircuitState.OPEN, CircuitState.HALF_OPEN, CircuitState.CLOSED]


def test_trial_failure_reopens_the_circuit():
    breaker, clock, _ = make()
    fail(breaker, 3)
    clock.now = 30.0
    breaker.before_call()
    breaker.record_failure()
    assert breaker.state is CircuitState.OPEN
    clock.now = 59.0  # the recovery timer restarted at t=30
    assert breaker.state is CircuitState.OPEN


def test_aborted_trial_does_not_block_the_breaker_forever():
    breaker, clock, _ = make()
    fail(breaker, 3)
    clock.now = 30.0
    breaker.before_call()
    breaker.abort_call()  # for example the request was cancelled
    breaker.before_call()  # a new trial is allowed


def test_late_success_does_not_close_an_open_circuit():
    breaker, _, _ = make()
    fail(breaker, 3)
    breaker.record_success()
    assert breaker.state is CircuitState.OPEN


def test_retry_delay_uses_exponential_backoff_with_full_jitter():
    policy = RetryPolicy(max_attempts=5, base_delay=0.1, max_delay=0.5)
    assert policy.delay(1, rng=lambda: 1.0) == pytest.approx(0.1)
    assert policy.delay(2, rng=lambda: 1.0) == pytest.approx(0.2)
    assert policy.delay(3, rng=lambda: 1.0) == pytest.approx(0.4)
    assert policy.delay(4, rng=lambda: 1.0) == pytest.approx(0.5)  # capped
    assert policy.delay(4, rng=lambda: 0.0) == 0.0  # full jitter can be zero
    assert policy.delay(2, rng=lambda: 0.5) == pytest.approx(0.1)
