# CLAUDE.md

Context for Claude Code and for future sessions. Keep this file short and current.

## What this project is

A personal practice project: an integration service in front of a mock core banking system.
Goal: learn, end to end, how to build a safe banking integration (idempotency, resilience,
reconciliation, observability, Kubernetes deploy). The owner prefers to understand the
reasoning before implementing, so explain decisions and record them as ADRs.

## Commands

```bash
make install        # pip install -e ".[dev]"
make test           # pytest (86 tests, ~2 s)
make lint           # ruff check + ruff format --check
make format
make run-core       # mock core :8081
make run-api        # service :8080
make smoke          # curl checks against a running instance
make helm-template  # then helm-dry-run, THEN helm-install
```

## Architecture rules (do not break)

- Dependencies point inward: `domain` <- `application` <- (`api`, `adapters`, `infrastructure`).
- `domain` and `application` never import `adapters`, `api`, `httpx`, or `fastapi`.
- Only `adapters/corebanking` knows the core's wire format (`wire.py`, `mappers.py`).
- Money is `Decimal`, never `float`. API amounts are decimal strings (`"100.00"`).
- A timeout on a write means "unknown", never "failed". Leave the transfer `PENDING`.
- Persist the transfer BEFORE calling the core.
- Never log raw account numbers or secrets. Use `fields(...)` from `structured_logging` so masking applies.
- Metric labels use route templates, never raw paths.
- New important decision -> new ADR in `docs/adr/` (accepted ADRs are not edited; supersede them).

## Conventions

- Commits: Conventional Commits, in English (`feat: ...`, `fix: ...`, `docs: ...`).
- Branches: `type/<ticket>-<short-kebab-objective>`, in English.
- Directory and file names: English. Only the content of `docs/` is Portuguese (pt-BR).
- Follow each tool's official docs (Kubernetes, Helm, Terraform, CI/CD) and current community practice.
- Run a dry run before any destructive command (`make helm-dry-run`, `make kind-down` needs `CONFIRM=yes`).
- Tests: `tests/unit`, `tests/contract`, `tests/integration`. Integration tests run in-process through `httpx.ASGITransport` (no network).

## Known limitations

- In-memory repository: restart loses transfers; chart runs 1 replica with `Recreate`.
- Static API keys (dev defaults, lab only).
- Reconciliation has no row locking (needs a database).

## Next steps (see docs/roadmap.md)

1. Fail closed on default API keys (security review finding): refuse to start with the
   built-in keys unless a dev flag is set; Helm `required` for secrets; new ADR.
2. Phase 3: PostgreSQL repository (`UNIQUE` idempotency key, Alembic, `FOR UPDATE SKIP LOCKED`), then 2+ replicas.
3. Phase 5: OpenTelemetry traces, SLOs, alerts.

## Session log

### 2026-10-26: initial scaffold
- Chose: Python + FastAPI, read-first-then-writes scope, in-process mock core, Kind + Helm.
- Built: domain, application, anti-corruption adapter, retry + circuit breaker, reconciliation,
  masked logs, metrics, OpenAPI contract, mock core with fault injection, 86 tests (all passing),
  Dockerfile (2 targets), Kind config, Helm chart, Makefile, CI workflow, docs and 5 ADRs.
- Verified: tests, ruff, both services over real HTTP with curl (including a real 2 s timeout
  after commit, resolved by the duplicate-reference path).
- Not verified: Docker build, Kind, Helm (no daemon or binaries in the build environment).

### 2026-10-26: Git repo + Docker/Kind/Helm validation
- Repo pushed to github.com/alisson92/core-banking-integration (`main`).
- Validated: `docker-build`, `kind-up`, `kind-load`, `helm-lint`, `helm-template`,
  `helm-dry-run`, `helm-install` (Helm 4.3, Kubernetes 1.34) and `smoke` through port-forward.
  `readOnlyRootFilesystem` works; 0 restarts.
- Fixed: Windows `*:Zone.Identifier` files broke `helm lint` (added `.helmignore`);
  Makefile cluster targets now pin `KUBE_CONTEXT` (default `kind-cbi-lab`).
- Open: default API keys are fail-open; uvicorn access log duplicates the JSON access log.
