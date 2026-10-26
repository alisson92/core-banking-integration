"""Retry policy and circuit breaker, small and dependency-free so you can read them end to end."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from core_integration.domain.errors import CircuitOpen


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Exponential backoff with FULL jitter.

    delay = random(0, min(max_delay, base * 2^(attempt-1)))
    Jitter spreads retries in time, so many clients do not hit a recovering core together.
    """

    max_attempts: int = 3
    base_delay: float = 0.1
    max_delay: float = 2.0

    def delay(self, attempt: int, rng: Callable[[], float] = random.random) -> float:
        ceiling = min(self.max_delay, self.base_delay * (2 ** (attempt - 1)))
        return rng() * ceiling


class CircuitState(StrEnum):
    CLOSED = "closed"  # normal: calls go through
    OPEN = "open"  # too many failures: calls are refused immediately
    HALF_OPEN = "half_open"  # testing: exactly one trial call is allowed


class CircuitBreaker:
    """Consecutive-failure circuit breaker. Single event loop, so no locks are needed."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        on_state_change: Callable[[CircuitState], None] | None = None,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._clock = clock
        self._on_state_change = on_state_change or (lambda _state: None)
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._trial_in_flight = False

    @property
    def state(self) -> CircuitState:
        if (
            self._state is CircuitState.OPEN
            and self._clock() - self._opened_at >= self._recovery_timeout
        ):
            self._transition(CircuitState.HALF_OPEN)
        return self._state

    def before_call(self) -> None:
        state = self.state
        if state is CircuitState.OPEN:
            raise CircuitOpen("circuit breaker is open")
        if state is CircuitState.HALF_OPEN:
            if self._trial_in_flight:
                raise CircuitOpen("circuit breaker is half-open and a trial call is running")
            self._trial_in_flight = True

    def record_success(self) -> None:
        self._trial_in_flight = False
        if self.state is CircuitState.OPEN:
            return  # a late answer from a call that started before we opened: ignore it
        self._failures = 0
        if self._state is not CircuitState.CLOSED:
            self._transition(CircuitState.CLOSED)

    def record_failure(self) -> None:
        self._trial_in_flight = False
        if self.state is CircuitState.HALF_OPEN:
            self._open()
            return
        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._open()

    def abort_call(self) -> None:
        """The call ended without a verdict (for example, it was cancelled)."""
        self._trial_in_flight = False

    def _open(self) -> None:
        self._opened_at = self._clock()
        self._transition(CircuitState.OPEN)

    def _transition(self, new_state: CircuitState) -> None:
        if new_state is self._state:
            return
        self._state = new_state
        self._on_state_change(new_state)
