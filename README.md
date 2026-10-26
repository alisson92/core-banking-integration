# Core Banking Integration

A practice project: an **integration service** in front of a **(mock) core banking system**.

It shows how to do the hard parts of a banking integration safely:

- an **anti-corruption layer**, so the core's ugly legacy format never leaks into our code
- **idempotent transfers**, so money never moves twice
- **timeouts, retries with jitter, and a circuit breaker**
- **reconciliation**, for the moment when we do not know what happened
- **safe logs** (account numbers masked) and Prometheus **metrics**
- a mock core with **fault injection**, so you can break things on purpose
- deploy files for **Kind + Helm**

Stack: Python 3.11+, FastAPI, httpx, pydantic, pytest.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
make install
make test            # 86 tests, about 2 seconds

make run-core        # terminal 1: mock core on :8081
make run-api         # terminal 2: our service on :8080 (docs at /docs)
make smoke           # terminal 3: end-to-end check
```

Try it:

```bash
curl -s -H 'X-API-Key: dev-service-key' localhost:8080/v1/accounts/0001234567/balance

curl -s -H 'X-API-Key: dev-service-key' -H 'Idempotency-Key: my-first-transfer' \
     -H 'Content-Type: application/json' \
     -d '{"source_account":"0001234567","destination_account":"0007654321","amount":"100.00"}' \
     localhost:8080/v1/transfers
```

Send the second command twice. The second answer is a replay (`200`), and the balance changes only once.

## Project layout

```
api/openapi.yaml            public contract (written before the code)
src/core_integration/       the service
  domain/                   Money, Transfer state machine, errors (no frameworks)
  application/              use cases and ports (interfaces)
  adapters/corebanking/     the ONLY place that knows the core's format
  infrastructure/           retry, circuit breaker, repository, settings
  observability/            masked JSON logs, Prometheus metrics
  api/                      FastAPI routes, errors, middleware
mocks/core_banking_mock/    the fake core, with fault injection
tests/                      unit, contract and integration tests
deploy/                     Dockerfile, Kind config, Helm chart
docs/                       architecture, ADRs, roadmap, learning guide (in Portuguese)
```

## Where to start reading

1. `docs/learning-guide.md`: reading order, hands-on experiments, exercises.
2. `docs/architecture.md`: diagrams and the reasoning.
3. `docs/adr/`: one short document per important decision.
4. `docs/roadmap.md`: what is done and what comes next (PostgreSQL is next).

## Status

Works and is tested: the whole Python service, the mock core, and the tests.
The Docker images, the Kind cluster and the Helm chart were validated end to end
(Docker 29, Kind 0.30 / Kubernetes 1.34, Helm 4.3): `make smoke` passes against the release.

## Known limitations

Transfers are kept **in memory**, so the Helm chart runs a single replica. Replacing this with
PostgreSQL is Phase 3 in the roadmap. This is a learning project: do not use it with real money.
