.PHONY: help install test test-unit test-functional test-all lint format clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ''
	@echo 'For runtime operations (start/stop/logs/monitor), use: itsup --help'

install: ## Install all dependencies (Docker, SOPS, Python packages)
	@./bin/install.sh

test-unit: ## Run unit tests (fast)
	./bin/test.sh

test-functional: ## Run functional tests (with real tools in Docker)
	docker build -t itsup-test -f tests/Dockerfile .
	docker run --rm itsup-test

test-all: test-unit test-functional ## Run both unit and functional tests

test: test-unit ## Run unit tests (default, alias for test-unit)

format: ## Format code
	./bin/format.sh

lint: ## Run linter
	./bin/lint.sh

clean: ## Remove generated artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete
	find . -type f -name '.coverage' -delete
