"""Fault injection for the mock core.

Real cores fail in ugly ways. These switches let you practice those failures
on demand, without waiting for a real incident.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class FaultConfig:
    # Extra delay added to every /core request (milliseconds).
    latency_ms: int = 0
    # Probability (0.0 - 1.0) of answering HTTP 500 on a /core request.
    error_rate: float = 0.0
    # The next N /core requests answer HTTP 503 (nothing is applied).
    fail_next: int = 0
    # The classic nightmare: the transfer IS committed, but the answer is slow.
    # The client may time out and never learn that the money moved.
    slow_after_commit_ms: int = 0
    slow_after_commit_next: int = 0

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)

    def reset(self) -> None:
        self.latency_ms = 0
        self.error_rate = 0.0
        self.fail_next = 0
        self.slow_after_commit_ms = 0
        self.slow_after_commit_next = 0
