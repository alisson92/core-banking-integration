"""Configuration from environment variables (prefix CBI_). Secrets come from the environment,
which in Kubernetes is filled from a Secret. Never hard-code real secrets."""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SERVICE_API_KEY = "dev-service-key"
DEFAULT_CORE_API_KEY = "core-dev-key"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CBI_", extra="ignore")

    core_base_url: str = "http://localhost:8081"
    core_api_key: SecretStr = SecretStr(DEFAULT_CORE_API_KEY)
    service_api_key: SecretStr = SecretStr(DEFAULT_SERVICE_API_KEY)

    # Timeouts and retries (see docs/adr/0003)
    core_timeout_seconds: float = Field(2.0, gt=0)
    read_max_attempts: int = Field(3, ge=1)
    write_max_attempts: int = Field(2, ge=1)
    backoff_base_seconds: float = Field(0.1, ge=0)
    backoff_max_seconds: float = Field(2.0, ge=0)

    # Circuit breaker
    breaker_failure_threshold: int = Field(5, ge=1)
    breaker_recovery_seconds: float = Field(30.0, gt=0)

    # Reconciliation loop (0 disables the background loop)
    reconcile_interval_seconds: float = Field(60.0, ge=0)
    reconcile_min_age_seconds: float = Field(30.0, ge=0)

    log_level: str = "INFO"
