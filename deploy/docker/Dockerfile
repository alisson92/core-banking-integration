# syntax=docker/dockerfile:1
#
# One Dockerfile, two images (build targets):
#   docker build --target integration -t cbi/integration:dev -f deploy/docker/Dockerfile .
#   docker build --target mock-core   -t cbi/mock-core:dev   -f deploy/docker/Dockerfile .

FROM python:3.13-slim AS builder
WORKDIR /build
COPY pyproject.toml ./
COPY src ./src
COPY mocks ./mocks
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.13-slim AS runtime-base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
# Non-root user. The numeric UID lets Kubernetes verify runAsNonRoot.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY --from=builder /install /usr/local
USER 10001

FROM runtime-base AS integration
EXPOSE 8080
CMD ["uvicorn", "core_integration.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]

FROM runtime-base AS mock-core
EXPOSE 8081
CMD ["uvicorn", "core_banking_mock.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8081"]
