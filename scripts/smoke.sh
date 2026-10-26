#!/usr/bin/env bash
# Smoke test against a running instance (local uvicorn or a kubectl port-forward).
#
#   BASE_URL=http://localhost:8080 API_KEY=dev-service-key scripts/smoke.sh
#
# Note: it creates one small transfer (1.00) on every run.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
API_KEY="${API_KEY:-dev-service-key}"
KEY="smoke-$(date +%s)-${RANDOM}"
BODY='{"source_account":"0001234567","destination_account":"0007654321","amount":"1.00"}'

status() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

check() { # check <name> <expected status> <actual status>
  if [ "$2" = "$3" ]; then
    echo "ok    $1 (HTTP $3)"
  else
    echo "FAIL  $1: expected HTTP $2, got HTTP $3"
    exit 1
  fi
}

check "liveness"                    200 "$(status "$BASE_URL/health/live")"
check "readiness"                   200 "$(status "$BASE_URL/health/ready")"
check "balance without API key"     401 "$(status "$BASE_URL/v1/accounts/0001234567/balance")"
check "balance"                     200 "$(status -H "X-API-Key: $API_KEY" "$BASE_URL/v1/accounts/0001234567/balance")"
check "transfer"                    201 "$(status -X POST -H "X-API-Key: $API_KEY" -H "Idempotency-Key: $KEY" -H 'Content-Type: application/json' -d "$BODY" "$BASE_URL/v1/transfers")"
check "transfer replay (same key)"  200 "$(status -X POST -H "X-API-Key: $API_KEY" -H "Idempotency-Key: $KEY" -H 'Content-Type: application/json' -d "$BODY" "$BASE_URL/v1/transfers")"
check "transfer without key"        400 "$(status -X POST -H "X-API-Key: $API_KEY" -H 'Content-Type: application/json' -d "$BODY" "$BASE_URL/v1/transfers")"
echo "smoke test passed"
