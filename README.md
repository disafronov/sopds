# Simple OPDS Server (SOPDS)

> A Django-based OPDS catalog server for e-book collections.
> Fork of [mitshel/sopds](https://github.com/mitshel/sopds/) by Dmitry Shelepnev.

## Features

- **OPDS 1.2 feed** at `/opds/` for OPDS-compatible reading apps (KOReader, FBReader, etc.)
- **Web UI** at `/web/` for browsing the catalog in a browser
- **Book formats**: FB2, EPUB, MOBI
- **FB2 conversion** to EPUB/MOBI on download
- **Scheduled scanning** via APScheduler with cron-like scheduling
- **INPX archive support** for batch metadata import
- **ZIP archive scanning** with configurable codepage
- **PostgreSQL or MariaDB** database backend
- **Parallel scanning** with a configurable process pool
- **Docker image** with multi-stage build (Ubuntu Noble + uv)
- **Health checks** (liveness and readiness probes)
- **Admin interface** for runtime configuration via django-constance
- **Whitenoise** for static file serving in production

## Requirements

- Python >= 3.12
- Django 5.2
- PostgreSQL 17 or MariaDB LTS
- Docker (optional)
- [uv](https://docs.astral.sh/uv/) package manager

## Quick Start

### Local Development

```bash
git clone https://github.com/disafronov/sopds.git
cd sopds

# Install dependencies (uv + pre-commit hooks)
make install

# Create .env from example
cp env.example .env
# Edit .env: set DJANGO_SECRET_KEY, DATABASE_URL, SOPDS_ROOT_LIB

# Apply migrations and start dev server + scanner
make run
```

The dev server starts at `http://0.0.0.0:8000/`. If `DJANGO_SUPERUSER_*`
variables are set in `.env`, an admin user is created automatically.

`DATABASE_URL` is required. For local development, use Docker Compose
to spin up the database services (see below).

### Docker Compose

For local development with PostgreSQL, MariaDB, and an SMTP sink (Mailpit):

```bash
docker compose up -d

# Then run locally against either database container
cp env.example .env
# Set DATABASE_URL to one of the examples in .env
make run
```

The MariaDB application database must be created with `utf8mb4` and
`utf8mb4_nopad_bin` before migrations are applied. The development Compose
service sets these as server defaults so application and test databases inherit
them. Setting a collation only in `DATABASE_URL` configures the connection, not
the database schema.

### Docker Image

```bash
docker build -t sopds .
docker run --rm -p 8000:8000 \
  -e DJANGO_SECRET_KEY=change-me \
  -e DJANGO_DEBUG=False \
  -e DATABASE_URL=postgres://sopds:sopds@host.docker.internal:5432/sopds \
  -v "$(pwd)/books:/books" \
  sopds
```

Or via Makefile:

```bash
make docker-build   # docker build -t sopds .
make docker-run     # migrate + createsuperuser + start on :8000
make docker         # docker-build + docker-run
```

## Configuration

Settings are read from environment variables. See `env.example` for all options.

### Django

| Variable | Description | Default |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Django `SECRET_KEY`. Required. | none |
| `DJANGO_DEBUG` | Debug mode (`1`/`true`/`yes`/`on`). | `False` |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated `ALLOWED_HOSTS`. | `*` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | CSRF trusted origins. | empty |
| `DJANGO_SECURE_SSL_REDIRECT` | Redirect HTTP requests to HTTPS. | `False` |
| `DJANGO_SESSION_COOKIE_SECURE` | Send the session cookie over HTTPS only. | `False` |
| `DJANGO_CSRF_COOKIE_SECURE` | Send the CSRF cookie over HTTPS only. | `False` |
| `DJANGO_SECURE_HSTS_SECONDS` | HSTS duration; `0` disables HSTS. | `0` |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` | Include subdomains in HSTS. | `False` |
| `DJANGO_SECURE_HSTS_PRELOAD` | Add the HSTS preload directive. | `False` |

### Database

| Variable | Description | Default |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL or MariaDB connection URL. | **required** |

### Server

| Variable | Description | Default |
| --- | --- | --- |
| `HOST` | Bind address for dev server. | `0.0.0.0` |
| `PORT` | Bind port for dev server. | `8000` |
| `GUNICORN_WORKERS` | Gunicorn web worker processes. | `2` |

### Superuser (used by `make run` and Docker entrypoint)

| Variable | Description |
| --- | --- |
| `DJANGO_SUPERUSER_USERNAME` | Admin username |
| `DJANGO_SUPERUSER_PASSWORD` | Admin password |
| `DJANGO_SUPERUSER_EMAIL` | Admin email |

### SOPDS Scanner

| Variable | Description | Default |
| --- | --- | --- |
| `SOPDS_ROOT_LIB` | Root directory for books. | `books/` |
| `SOPDS_ZIP_ENABLE` | Enable scanning ZIP archives. | `True` |
| `SOPDS_ZIP_CODEPAGE` | Codepage for ZIP filenames. | `cp866` |
| `SOPDS_DELETE_LOGICAL` | Logical deletion of removed books. | `False` |
| `SOPDS_INPX_ENABLE` | Enable INPX archive scanning. | `False` |
| `SOPDS_INPX_SKIP_UNCHANGED` | Skip unchanged INPX files. | `True` |
| `SOPDS_SCAN_START_DIRECTLY` | Request a one-shot scan from the scheduler. | `False` |
| `SOPDS_SCAN_WORKERS` | Scanner worker processes; `0` uses `os.cpu_count()`. | `0` |

Additional knobs are available via the Django admin (`/admin/`) under
django-constance.

## Management Commands

All commands are run via `uv run python manage.py <command>` (or `make` shortcuts).

| Command | Description |
| --- | --- |
| `dev` | Start `runserver` + scanner for development. |
| `start` | Start gunicorn + scanner for production (used by Docker). |
| `sopds_scanner [scan\|start]` | Run a one-shot scan or the foreground scheduler. |
| `sopds_util [clear\|info\|setconf\|getconf\|pg_optimize\|...]` | Utilities: DB info, config management, genre import/export. |

Run `python manage.py <command> --help` for full usage details.

## API Endpoints

| Path | Description |
| --- | --- |
| `/` | Redirects to web UI (`/web/`) |
| `/web/` | Web browsing interface |
| `/opds/` | OPDS 1.2 catalog feed |
| `/admin/` | Django admin interface |
| `/health/liveness/` | Liveness probe (returns 200) |
| `/health/readiness/` | Readiness probe (checks DB connectivity) |

## Development

### Makefile Targets

| Target | Description |
| --- | --- |
| `make install` | Install Python + dependencies + pre-commit hooks |
| `make format` | Auto-format with black + isort |
| `make lint` | Check with black, isort, flake8, mypy (strict), bandit |
| `make test` | Run pytest with coverage |
| `make all` | lint + test + dead-code (vulture) |
| `make audit` | Check dependencies for known vulnerabilities |
| `make dead-code` | Detect unused code with vulture |
| `make locale` | Update and compile translation catalogs |
| `make migrate` | Apply database migrations |
| `make makemigrations` | Create new migrations |
| `make run` | Migrate + create superuser + dev server + scanner |
| `make scanner` | Run scanner standalone (APScheduler loop) |
| `make docker-build` | Build Docker image |
| `make docker-run` | Run Docker container |
| `make docker` | Build + run Docker container |
| `make clean` | Remove caches, .venv, coverage outputs |

### Linting

- **black** (line-length 88)
- **isort** (black profile)
- **flake8** (max-line-length 88)
- **mypy** (strict mode with django-stubs)
- **bandit** (security linter)

Pre-commit hooks are installed by `make install`.

### CI/CD

- **lint_and_test** -- runs `make all` + `make audit` on PRs
- **docker** -- builds and pushes Docker image to `ghcr.io` on tags
- **semantic-release** -- automated versioning on `main`/`release` branches

## Project Structure

```text
config/                 Django project configuration (settings, urls, wsgi)
opds_catalog/           Core app: models, scanner, OPDS feeds, middleware
web_backend/            Web UI app: views, templates, static assets
ops/                    Operations: dev/start launchers, health checks, supervisor
book_tools/             SOPDS book-format adapters and vendored parser forks
convert/                Bundled FB2 to EPUB/MOBI converter
assets/                 Front-end assets
books/                  Book storage directory (mounted as Docker volume)
```

## Versioning

This project uses [Semantic Versioning](https://semver.org/) with
[Conventional Commits](https://www.conventionalcommits.org/).
Releases are automated via [semantic-release](https://github.com/semantic-release/semantic-release).
