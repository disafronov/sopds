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
TOOLING_DATABASE_URL = postgres://unused:unused@127.0.0.1:5432/unused

UV = uv run
PYTEST_CMD = DJANGO_SECRET_KEY=$(TOOLING_SECRET_KEY) $(UV) python -m pytest -v -n auto
TEST_ARGS = $(if $(filter all,$(MAKECMDGOALS)),,$(filter-out test all,$(MAKECMDGOALS)))

DOCKER_IMAGE = sopds

DOCKER_RUN_OPTS = --rm \
	--read-only \
	--tmpfs /tmp \
	--add-host=host.docker.internal:host-gateway \
	$(if $(wildcard env.example),--env-file env.example,) \
	$(if $(wildcard env.docker),--env-file env.docker,) \
	$(if $(wildcard .env),--env-file .env,) \
	$(if $(wildcard .env.docker),--env-file .env.docker,) \
	-v "${PWD}/opds_catalog/tests/data":/books

.PHONY: all audit clean dead-code dev docker docker-build docker-run format help install lint locale makemigrations migrate migrate-mysql migrate-postgresql run scanner scan test test-mysql test-postgresql

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
	$(UV) black . && \
	$(UV) isort .

lint: ## Run linting tools
	@echo "Running linting tools..."
	$(UV) black --check . && \
	$(UV) isort --check-only . && \
	$(UV) flake8 . && \
	DATABASE_URL=$(TOOLING_DATABASE_URL) DJANGO_SECRET_KEY=$(TOOLING_SECRET_KEY) $(UV) mypy . && \
	$(UV) bandit -r -c pyproject.toml .

audit: ## Check dependencies for known vulnerabilities
	@echo "Auditing dependencies..."
	uv run pip-audit

dead-code: ## Check for dead code using vulture
	@echo "Checking for dead code..."
	uv run vulture

locale: ## Make and compile locale messages
	@echo "Making translation messages..."
	DATABASE_URL=$(TOOLING_DATABASE_URL) DJANGO_SECRET_KEY=$(TOOLING_SECRET_KEY) $(UV) python manage.py makemessages --no-obsolete --all --ignore=".venv/*" --ignore="staticfiles/*" --ignore="*/static/*" --ignore="*/tests/*" --ignore="conftest.py"
	@echo "Compiling translation messages..."
	DATABASE_URL=$(TOOLING_DATABASE_URL) DJANGO_SECRET_KEY=$(TOOLING_SECRET_KEY) $(UV) python manage.py compilemessages --ignore=".venv/*"

makemigrations: ## Create new migrations
	@echo "Creating migrations..."
	DJANGO_SECRET_KEY=$(TOOLING_SECRET_KEY) $(UV) python manage.py makemigrations

migrate-postgresql: ## Apply database migrations to PostgreSQL
	@echo "Applying migrations to PostgreSQL..."
	DATABASE_URL="$(DATABASE_URL_POSTGRESQL)" DJANGO_SECRET_KEY=$(TOOLING_SECRET_KEY) $(UV) python manage.py migrate

migrate-mysql: ## Apply database migrations to MySQL/MariaDB
	@echo "Applying migrations to MySQL/MariaDB..."
	DATABASE_URL="$(DATABASE_URL_MYSQL)" DJANGO_SECRET_KEY=$(TOOLING_SECRET_KEY) $(UV) python manage.py migrate

migrate: migrate-postgresql migrate-mysql ## Apply migrations to both supported databases

test-postgresql: ## Run tests on PostgreSQL
	@echo "Running tests on PostgreSQL..."
	DATABASE_URL="$(DATABASE_URL_POSTGRESQL)" $(PYTEST_CMD) $(TEST_ARGS)

test-mysql: ## Run tests on MySQL/MariaDB
	@echo "Running tests on MySQL/MariaDB..."
	DATABASE_URL="$(DATABASE_URL_MYSQL)" $(PYTEST_CMD) $(TEST_ARGS)

test: locale migrate test-postgresql test-mysql ## Run tests on both supported databases

all: lint test dead-code ## Run all checks
	@echo "All checks completed successfully!"

run: locale ## Start the app on selected DATABASE_URL (with migrations)
	@echo "Running Django dev server + scanner..."
	DJANGO_SECRET_KEY=$(TOOLING_SECRET_KEY) $(UV) python manage.py migrate
	@if [ -n "$$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$$DJANGO_SUPERUSER_PASSWORD" ] && [ -n "$$DJANGO_SUPERUSER_EMAIL" ]; then \
		echo "Ensuring Django superuser exists..."; \
		$(UV) python manage.py createsuperuser --noinput || true; \
	else \
		echo "Skipping createsuperuser (set DJANGO_SUPERUSER_USERNAME/PASSWORD/EMAIL to enable)."; \
	fi
	DJANGO_SECRET_KEY=$(TOOLING_SECRET_KEY) $(UV) python manage.py dev

scanner: ## Run the sopds scanner (APScheduler)
	@echo "Running sopds scanner..."
	$(UV) python manage.py sopds_scanner start

scan: ## Run the sopds scanner oneshot scan
	@echo "Running sopds scanner oneshot scan..."
	$(UV) python manage.py sopds_scanner scan

clean: ## Clean caches and coverage outputs
	@echo "Cleaning cache and temporary files..."
	rm -rf .mypy_cache/ .pytest_cache/ .venv/ build/ dist/ htmlcov/ .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

docker-build: ## Build Docker image
	@echo "Building Docker image..."
	docker build -t $(DOCKER_IMAGE) .

docker-run: ## Run Docker container (migrate → createsuperuser → start)
	@echo "Running migrations..."
	docker run $(DOCKER_RUN_OPTS) $(DOCKER_IMAGE) migrate
	@if [ -n "$$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$$DJANGO_SUPERUSER_PASSWORD" ] && [ -n "$$DJANGO_SUPERUSER_EMAIL" ]; then \
		echo "Ensuring Django superuser exists..."; \
		docker run $(DOCKER_RUN_OPTS) $(DOCKER_IMAGE) createsuperuser --noinput || true; \
	else \
		echo "Skipping createsuperuser (set DJANGO_SUPERUSER_USERNAME/PASSWORD/EMAIL to enable)."; \
	fi
	@echo "Starting server..."
	docker run $(DOCKER_RUN_OPTS) -p 8000:8000 $(DOCKER_IMAGE)

docker: docker-build docker-run ## Build and run Docker container
	@echo "Docker container built and running!"
