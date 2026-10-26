"""Domain errors.

The API layer maps each family to an HTTP status. The families matter:

- BusinessRuleViolation: the core understood us and said "no". Final answer.
- CoreUnavailable:       we do not know what happened. Retry later, never assume.
- CoreProtocolError:     the core answered something we cannot understand. Needs a human.
"""

from __future__ import annotations


class DomainError(Exception):
    default_code = "DOMAIN_ERROR"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code


class InvalidRequest(DomainError):
    default_code = "INVALID_REQUEST"


class Unauthorized(DomainError):
    default_code = "UNAUTHORIZED"


class IdempotencyConflict(DomainError):
    default_code = "IDEMPOTENCY_KEY_REUSED"


class TransferNotFound(DomainError):
    default_code = "TRANSFER_NOT_FOUND"


class InvalidTransition(DomainError):
    """A bug: someone tried an impossible state change on a transfer."""

    default_code = "INVALID_TRANSITION"


# --- final answers from the core -------------------------------------------------
class BusinessRuleViolation(DomainError):
    default_code = "BUSINESS_RULE_VIOLATION"


class AccountNotFound(BusinessRuleViolation):
    default_code = "ACCOUNT_NOT_FOUND"


class AccountNotAvailable(BusinessRuleViolation):
    default_code = "ACCOUNT_NOT_AVAILABLE"


class InsufficientFunds(BusinessRuleViolation):
    default_code = "INSUFFICIENT_FUNDS"


# --- we do not know what happened ------------------------------------------------
class CoreUnavailable(DomainError):
    default_code = "CORE_UNAVAILABLE"

    def __init__(
        self, message: str, code: str | None = None, *, outcome_unknown: bool = False
    ) -> None:
        super().__init__(message, code)
        # True when the request may have reached the core and may have been applied.
        self.outcome_unknown = outcome_unknown


class CircuitOpen(CoreUnavailable):
    """The circuit breaker refused to call the core (it is protecting us and the core)."""

    default_code = "CIRCUIT_OPEN"


class CoreProtocolError(DomainError):
    default_code = "CORE_PROTOCOL_ERROR"
