.DEFAULT_GOAL := help

PYTHON       ?= python3
KIND_CLUSTER ?= cbi-lab
# Pin every cluster command to the Kind context, so a Makefile target never hits whatever
# context happens to be active (for example a production EKS cluster).
KUBE_CONTEXT ?= kind-$(KIND_CLUSTER)
NAMESPACE    ?= cbi
RELEASE      ?= cbi
IMAGE_TAG    ?= dev
CHART        := deploy/helm/core-banking-integration
BASE_URL     ?= http://localhost:8080

.PHONY: help install lint format test run-core run-api smoke docker-build kind-up kind-load \
        helm-lint helm-template helm-dry-run helm-install helm-uninstall port-forward kind-down

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

# ----------------------------------------------------------------- development
install: ## Install the project and dev tools (use a virtualenv)
	$(PYTHON) -m pip install -e ".[dev]"

lint: ## Check style and common bugs
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format: ## Format the code
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check . --fix

test: ## Run all tests
	$(PYTHON) -m pytest

run-core: ## Run the mock core on :8081
	PYTHONPATH=src:mocks $(PYTHON) -m uvicorn core_banking_mock.main:create_app --factory --port 8081

run-api: ## Run the integration service on :8080 (start run-core first)
	PYTHONPATH=src:mocks $(PYTHON) -m uvicorn core_integration.api.app:create_app --factory --port 8080

smoke: ## Smoke test a running instance (BASE_URL=http://localhost:8080)
	BASE_URL=$(BASE_URL) scripts/smoke.sh

# ------------------------------------------------------------------ containers
docker-build: ## Build both images
	docker build --target integration -t cbi/integration:$(IMAGE_TAG) -f deploy/docker/Dockerfile .
	docker build --target mock-core   -t cbi/mock-core:$(IMAGE_TAG)   -f deploy/docker/Dockerfile .

# ------------------------------------------------------------------ kubernetes
kind-up: ## Create the Kind cluster (skips if it already exists)
	@kind get clusters | grep -qx "$(KIND_CLUSTER)" && echo "cluster $(KIND_CLUSTER) already exists" \
		|| kind create cluster --config deploy/kind/kind-config.yaml

kind-load: ## Load the local images into the Kind cluster
	kind load docker-image cbi/integration:$(IMAGE_TAG) cbi/mock-core:$(IMAGE_TAG) --name $(KIND_CLUSTER)

helm-lint: ## Lint the chart
	helm lint $(CHART)

helm-template: ## Render the chart locally (no cluster needed). Read the output before installing.
	helm template $(RELEASE) $(CHART) --namespace $(NAMESPACE)

helm-dry-run: ## Ask the cluster to validate the install without changing anything
	helm upgrade --install $(RELEASE) $(CHART) --namespace $(NAMESPACE) --create-namespace --dry-run=server --kube-context $(KUBE_CONTEXT)

helm-install: ## Install or upgrade the release (run helm-dry-run first!)
	helm upgrade --install $(RELEASE) $(CHART) --namespace $(NAMESPACE) --create-namespace --wait --kube-context $(KUBE_CONTEXT)

helm-uninstall: ## Remove the release
	helm uninstall $(RELEASE) --namespace $(NAMESPACE) --kube-context $(KUBE_CONTEXT)

port-forward: ## Expose the integration service on localhost:8080
	kubectl --context $(KUBE_CONTEXT) -n $(NAMESPACE) port-forward svc/$(RELEASE)-core-banking-integration-integration 8080:8080

kind-down: ## Delete the Kind cluster (needs CONFIRM=yes)
	@test "$(CONFIRM)" = "yes" || { echo "This deletes the cluster $(KIND_CLUSTER). Run: make kind-down CONFIRM=yes"; exit 1; }
	kind delete cluster --name $(KIND_CLUSTER)
