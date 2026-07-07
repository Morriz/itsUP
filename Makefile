.PHONY: help install install-runtime uninstall-runtime test test-integration test-all lint format clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ''
	@echo 'For runtime operations (start/stop/logs/monitor), use: itsup --help'

install: ## Install dependencies only (system tools, Python venv, git hooks) — never starts the runtime
	@./bin/install.sh

install-runtime: ## Make this host a live deployment: install host integration (systemd/launchd) and start the stack
	@test -x .venv/bin/itsup || { echo "Run 'make install' first — no .venv/bin/itsup found"; exit 1; }
	@./bin/install-bringup.sh

uninstall-runtime: ## Decommission this host: stop the whole stack, flush monitor rules, remove host integration
	@./bin/uninstall-runtime.sh

test: ## Fast test gate (excludes the integration tier)
	@./bin/test.sh

test-integration: ## Integration tier — real sops/age/git, slower
	@uv run pytest -m integration

test-all: ## Every tier (fast + integration)
	@uv run pytest -m 'integration or not integration'

format: ## Format code
	@FILES_FROM="$(FILES_FROM)" ./bin/format.sh

lint: ## Run linter
	@FILES_FROM="$(FILES_FROM)" ./bin/lint.sh

clean: ## Remove generated artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete
	find . -type f -name '.coverage' -delete
