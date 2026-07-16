# Python version is pinned via `.python-version` (used by uv and CI).
PYTHON_VERSION := $(shell tr -d '[:space:]' < .python-version)

# Include env files for local development (not in CI).
ifeq ($(strip $(CI)),)
    ifneq (,$(wildcard .env))
        ifneq (,$(wildcard env.example))
            include env.example
        endif
        include .env
    else
        ifneq (,$(wildcard env.example))
            include env.example
        endif
    endif
    export
endif

TOOLING_SECRET_KEY = unsafe-secret-key-for-tooling

UV = uv run
PYTEST_CMD = DJANGO_SECRET_KEY=$(TOOLING_SECRET_KEY) $(UV) python -m pytest -v
COVERAGE_OPTS = --cov=. --cov-report=term-missing --cov-report=html

DOCKER_IMAGE = sopds
DOCKER_PORT = 8000

DOCKER_RUN_OPTS = --rm \
	--read-only \
	--tmpfs /tmp \
	--add-host=host.docker.internal:host-gateway \
	$(if $(wildcard env.example),--env-file env.example,) \
	$(if $(wildcard env.docker),--env-file env.docker,) \
	$(if $(wildcard .env),--env-file .env,)

# Phony targets
.PHONY: all audit clean dead-code docker docker-build docker-run format help install lint makemigrations migrate run test test-coverage

help: ## Show this help message
	@echo "Available commands:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort

install: ## Install dependencies
	@echo "Installing dependencies..."
	uv python install $(PYTHON_VERSION)
	uv sync --python $(PYTHON_VERSION)
	@echo "Installing pre-commit hooks..."
	uv run pre-commit install

format: ## Format code
	@echo "Formatting code..."
	$(UV) autoflake --in-place --remove-all-unused-imports --ignore-init-module-imports -r . && \
	$(UV) black . && \
	$(UV) isort .

lint: ## Run linting tools
	@echo "Running linting tools..."
	$(UV) black --check . && \
	$(UV) isort --check-only . && \
	$(UV) flake8 . && \
	DJANGO_SECRET_KEY=$(TOOLING_SECRET_KEY) $(UV) mypy . && \
	$(UV) bandit -r -c pyproject.toml .

audit: ## Check dependencies for known vulnerabilities
	@echo "Auditing dependencies..."
	uv run pip-audit

dead-code: ## Check for dead code using vulture
	@echo "Checking for dead code..."
	$(UV) vulture

makemigrations: ## Create new migrations
	@echo "Creating migrations..."
	DJANGO_SECRET_KEY=$(TOOLING_SECRET_KEY) $(UV) python manage.py makemigrations

migrate: ## Apply database migrations
	@echo "Applying migrations..."
	DJANGO_SECRET_KEY=$(TOOLING_SECRET_KEY) $(UV) python manage.py migrate

test: ## Run tests
	@echo "Running tests..."
	$(PYTEST_CMD)

test-coverage: ## Run tests with coverage
	@echo "Running tests with coverage..."
	$(PYTEST_CMD) $(COVERAGE_OPTS)

all: lint test dead-code ## Run lint, test, and dead-code check
	@echo "All checks completed successfully!"

run: migrate ## Apply migrations and run the Django dev server
	@echo "Running Django application locally..."
	DJANGO_SECRET_KEY=$(TOOLING_SECRET_KEY) $(UV) python manage.py runserver

clean: ## Clean cache and temporary files
	@echo "Cleaning cache and temporary files..."
	rm -rf .mypy_cache/ .pytest_cache/ .venv/ build/ dist/ htmlcov/ .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

docker-build: ## Build Docker image
	@echo "Building Docker image..."
	docker build -t $(DOCKER_IMAGE) .

docker-run: ## Run Docker container (migrate → start)
	@echo "Running migrations..."
	docker run $(DOCKER_RUN_OPTS) $(DOCKER_IMAGE) migrate
	@echo "Starting server..."
	docker run $(DOCKER_RUN_OPTS) -p $(DOCKER_PORT):$(DOCKER_PORT) $(DOCKER_IMAGE)

docker: docker-build docker-run ## Build and run Docker container
	@echo "Docker container built and running!"
