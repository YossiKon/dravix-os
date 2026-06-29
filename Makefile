# dravix-os — common tasks
.DEFAULT_GOAL := help

.PHONY: help install dev run discover test compile lint docker-build docker-up docker-down update-upstream

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install the core package (editable) into the current environment
	cd core && pip install -e .[dev]

dev: ## Run the service with autoreload
	cd core && uvicorn dravix.app:create_app --factory --reload --host 0.0.0.0 --port 8800

run: ## Run the service
	cd core && python -m dravix

discover: ## Probe the robot MCP URL + Home Assistant; write docs/capability-report.md
	cd core && python scripts/discover.py

test: ## Run tests
	cd core && pytest -q

compile: ## Syntax-check all Python sources
	cd core && python -m compileall -q dravix scripts

lint: ## Lint with ruff (if installed)
	cd core && ruff check dravix scripts || true

docker-build: ## Build the container image
	docker compose -f deploy/docker-compose.yml build

docker-up: ## Start the stack (detached)
	docker compose -f deploy/docker-compose.yml up -d

docker-down: ## Stop the stack
	docker compose -f deploy/docker-compose.yml down

update-upstream: ## Pull the latest m5stack/StackChan into vendor/ (reference only)
	git submodule update --remote --merge vendor/upstream || \
		echo "Run 'make vendor-init' first to add the upstream submodule."

vendor-init: ## Add m5stack/StackChan as the upstream submodule (run once)
	git submodule add https://github.com/m5stack/StackChan vendor/upstream
