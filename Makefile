.PHONY: help install test lint format validate apply rollout backup \
        dns-up dns-down dns-restart dns-logs \
        monitor-start monitor-stop monitor-cleanup monitor-logs monitor-report \
        start-proxy start-api start start-all restart-all \
        logs \
        clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Development
install: ## Install dependencies
	./bin/install.sh

test: ## Run all tests
	./bin/test.sh

lint: ## Run linter
	./bin/lint.sh

format: ## Format code
	./bin/format.sh

validate: ## Validate db.yml
	python3 bin/validate-db.py

# Deployment
apply: ## Apply configuration changes
	python3 bin/apply.py

rollout: ## Apply with zero-downtime rollout
	python3 bin/apply.py rollout

backup: ## Backup upstream directory to S3
	python3 bin/backup.py

dns-logs: ## Tail DNS honeypot logs
	@docker logs -f dns-honeypot || true

# Container Security Monitor
monitor-start: ## Start container security monitor and tail logs (FLAGS: --skip-sync --block --use-opensnitch)
	./bin/start-monitor.sh $(FLAGS)

monitor-stop: ## Stop container security monitor
	sudo pkill -f docker_monitor.py

monitor-cleanup: ## Run cleanup mode to review blacklist
	sudo python3 bin/docker_monitor.py --cleanup

monitor-logs: ## Tail security monitor logs
	@tail -f /var/log/compromised_container.log || true

monitor-report: ## Generate threat actor analysis report
	python3 bin/analyze_threats.py

# Service Management
start-proxy: ## Start proxy stack
	./bin/start-proxy.sh

start-api: ## Start API server
	./bin/start-api.sh

start: ## Start DNS, proxy, and API
	@$(MAKE) dns-up
	./bin/start-all.sh

start-all: start ## Alias for start

restart-all: ## Restart all containers except dns-honeypot
	./bin/restart-all.sh

logs: ## Tail all logs (Traefik access, API, errors) with flat formatting
	./bin/tail-logs.sh

# Cleanup
clean: ## Remove generated artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	find . -type f -name '*.pyo' -delete
	find . -type f -name '.coverage' -delete
