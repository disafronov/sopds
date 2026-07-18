# SOPDS

SOPDS (Simple OPDS) is an OPDS catalog server for e-books, built on Django. It
scans a directory of book files (fb2, epub, mobi, pdf, djvu), indexes their
metadata into a database, and exposes the collection both as an HTTP library
browsing UI and as an OPDS 1.2 feed for OPDS-compatible reading apps. It can
convert fb2 books to epub/mobi on download and optionally serve a Telegram bot
for search and download.

## Fork relationship

This repository is a soft fork of the original [**SOPDS**](https://github.com/mitshel/sopds/) by Dmitry Shelepnev. Upstream attribution and the original license are preserved:

- Original author: Dmitry V. Shelepnev
- Current maintainer / fork base: Dmitrii Safronov

This fork modernizes the toolchain (uv, Django 5.2, semantic-release CI, Docker
image) but keeps the original OPDS behavior and license intact.

## Requirements

- **Python**: 3.10, 3.11, or 3.12 (pinned to `3.12` via `.python-version`; CI
  and Docker use that version). Python 3.13 is not supported.
- **uv** — package and environment manager (<https://docs.astral.sh/uv/>).
- **PostgreSQL** 17 (recommended for concurrent scanning) or the default
  **SQLite** (`sqlite:///db.sqlite3`).
- **Django** 5.2.x.

Runtime system libraries are listed in the `Dockerfile` (libxml2, libxslt,
libjpeg, zlib, etc.); for local installs these come via `uv sync`.

## Installation (local development)

```bash
git clone https://github.com/disafronov/sopds.git
cd sopds

# Install the pinned Python and sync the environment (writes .venv, installs hooks)
make install

# Create your local env file from the example
cp env.example .env
#   edit .env: set SECRET_KEY, DJANGO_SECRET_KEY, DATABASE_URL, etc.

# Apply migrations
make migrate

# Create an admin user (optional; reads DJANGO_SUPERUSER_* from the Makefile env)
make run      # also runs createsuperuser (if DJANGO_SUPERUSER_* are set) + dev server
```

`make install` runs `uv python install`, `uv sync`, and `uv run pre-commit install`.
`make run` runs `manage.py migrate`, attempts `createsuperuser --noinput` when the
`DJANGO_SUPERUSER_*` env vars are present, then launches `manage.py dev`.

## Configuration

Settings are read from environment variables (see `sopds/settings.py`). The
Makefile auto-exports `env.example` and `.env` for local runs.

| Variable | Meaning | Default |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Django `SECRET_KEY`. Falls back to an insecure hardcoded key if unset. **Set it.** | hardcoded |
| `SECRET_KEY` | Legacy alias (not read by settings; `DJANGO_SECRET_KEY` wins). | – |
| `DJANGO_DEBUG` | Enable Django debug mode (`1`/`true`/`yes`/`on`). | `True` |
| `DEBUG` | Legacy alias (not read by settings). | – |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated `ALLOWED_HOSTS`. | `*` |
| `ALLOWED_HOSTS` | Legacy alias (not read by settings). | – |
| `DATABASE_URL` | Database DSN: `sqlite:///db.sqlite3` or `postgres://user:pass@host:port/db`. | `sqlite:///db.sqlite3` |
| `HOST` / `PORT` | Bind host/port for the dev server launcher. | `0.0.0.0` / `8000` |
| `SOPDS_USER` / `SOPDS_EMAIL` / `SOPDS_PASSWORD` | Example initial admin credentials (informational; `DJANGO_SUPERUSER_*` are what `make run` consumes). | – |
| `DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD` / `DJANGO_SUPERUSER_EMAIL` | Create an admin user via `createsuperuser --noinput` (used by `make run` and the container entrypoint). | – |

### Database

`DATABASE_URL` selects the engine:

- `sqlite:///...` → SQLite (single-user; scanning blocks reads).
- `postgres://` or `postgresql://` → Django `postgresql` backend (uses
  `psycopg2-binary`). Credentials are parsed from the URL.

Application behavior knobs (scanner schedule, book extensions, Telegram, covers,
etc.) live in **django-constance** (`CONSTANCE_CONFIG` in `sopds/settings.py`),
stored in the database and editable via the Django admin (`/admin/`). Many have
env overrides read at startup (e.g. `SOPDS_ROOT_LIB`, `SOPDS_ZIPSCAN`,
`SOPDS_INPX_ENABLE`, `SOPDS_SCAN_START_DIRECTLY`, ...); see `env.example`.

> **CI note:** `.github/workflows/lint_and_test.yaml` injects
> `DATABASE_HOST`/`DATABASE_PORT`/`DATABASE_NAME`/`DATABASE_USER`/`DATABASE_PASSWORD`,
> but `sopds/settings.py` only reads `DATABASE_URL`. The CI job relies on the
> default SQLite `DATABASE_URL` unless the workflow is updated to set `DATABASE_URL`.

## Running locally

```bash
# Dev: supervised runserver (0.0.0.0:8000) + scanner, with auto-reload
make run
python manage.py dev

# Production-style WSGI via gunicorn (2 workers, timeout 120) + scanner
python manage.py start
gunicorn sopds.wsgi:application --bind 0.0.0.0:8000
```

- `manage.py dev` launches `runserver 0.0.0.0:8000` and `sopds_scanner start` as
  supervised child processes. Use for local development only.
- `manage.py start` launches `gunicorn sopds.wsgi:application` and
  `sopds_scanner start` under the same supervisor — this is what the Docker image
  uses.

After startup, the catalog is served at:

- HTTP UI: `http://<host>:8000/`
- OPDS feed: `http://<host>:8000/opds/`
- Admin: `http://<host>:8000/admin/`
- Readiness probe: `http://<host>:8000/health/readiness/`

## Docker

The Dockerfile builds a `ubuntu:noble` image using the `astral-sh/uv` base for
dependency install. The image:

- Exposes port **8000**.
- Mounts a volume at **`/books`**.
- Runs `python3 manage.py collectstatic` at build time (served by whitenoise).
- Uses entrypoint `python3 manage.py` with default command `start` (i.e.
  `manage.py start` → gunicorn + scanner).

Build and run:

```bash
docker build -t sopds .
docker run --rm -p 8000:8000 \
  -e DJANGO_SECRET_KEY=change-me \
  -e DJANGO_DEBUG=False \
  -e DATABASE_URL=postgres://sopds:sopds@host.docker.internal:5432/sopds \
  -v "$(pwd)/books:/books" \
  sopds
```

The Makefile provides helpers:

```bash
make docker-build   # docker build -t sopds .
make docker-run     # migrate, createsuperuser (if DJANGO_SUPERUSER_* set), run on :8000
make docker         # docker-build + docker-run
```

`docker-run` auto-loads `env.example`, `env.docker`, and `.env` via
`--env-file` and adds `host.docker.internal` host mapping.

For local Postgres without production concerns, `compose.yml` provides a
`postgres:17` service and a `mailpit` SMTP sink (dev only — not for production).

## Management commands

All commands are standard Django management commands (`python manage.py <cmd>`),
run via `uv run` in this repo.

### `dev`

Start `runserver` and the scanner together (development only). No arguments.
Launches `sopds_scanner start` and `runserver 0.0.0.0:8000` as supervised
children. See `ops/management/commands/dev.py`.

### `start`

Start `gunicorn sopds.wsgi:application` and the scanner under a common supervisor
(no arguments). Used by the Docker image. See `ops/management/commands/start.py`.

### `sopds_scanner`

Scan the book collection. `help`: "Scan Books Collection."

```shell
python manage.py sopds_scanner [scan|start|stop|restart] [--verbose] [--daemon]
```

- `scan` — run a single one-time scan.
- `start` — run the APScheduler loop (scheduled scans per constance cron knobs).
- `stop` / `restart` — signal the running scanner via its pidfile.
- `--verbose` — also log to stdout.
- `--daemon` — detach to background (POSIX only; not used by Docker).

### `sopds_server`

HTTP/OPDS built-in server (legacy; prefer `start`/gunicorn). `help`:
"HTTP/OPDS built-in server."

```shell
python manage.py sopds_server [start|stop|restart] [--host H] [--port N] [--daemon]
```

- `--host` — bind address (default `0.0.0.0`).
- `--port` — port (default `8001`).
- `--daemon` — detach to background (POSIX only).

### `sopds_telebot`

Telegram bot engine. `help`: "SimpleOPDS Telegram Bot engine."

```shell
python manage.py sopds_telebot [start] [--verbose]
```

Runs the bot in the foreground. Requires `SOPDS_TELEBOT_API_TOKEN` (constance).
`--verbose` logs to stdout.

### `sopds_util`

Utilities. `help`: "Utils for SOPDS." Takes one or more positional subcommands:

```shell
python manage.py sopds_util [clear|info|save_mygenres|load_mygenres|setconf|getconf|pg_optimize] [--verbose] [--nogenres]
```

- `clear` — wipe the book DB and reload genre fixtures.
- `info` — print counts (books, catalogs, authors, genres, series).
- `save_mygenres` / `load_mygenres` — dump/load the genre directory to/from
  `opds_catalog/fixtures/mygenres.json`.
- `setconf <param> <value>` — set a constance config value.
- `getconf [param]` — show one or all config values.
- `pg_optimize` — PostgreSQL table optimization (`fillfactor=50` on the book table).
- `--verbose`, `--nogenres` — verbosity / skip genre reload on `clear`.

## Development & CI

### Makefile targets

| Target | What it does |
| --- | --- |
| `make install` | `uv python install` + `uv sync` + `pre-commit install`. |
| `make lint` | `black --check`, `isort --check-only`, `flake8`, `mypy .`, `bandit`. |
| `make test` | `pytest -v -n auto` with coverage. |
| `make all` | `lint` + `test` + `dead-code` (vulture). |
| `make format` | `black` + `isort` (in-place). |
| `make migrate` / `makemigrations` | Django migrations. |
| `make run` / `scanner` | Dev server / standalone scanner. |
| `make audit` | `pip-audit` on dependencies. |
| `make dead-code` | `vulture` check. |
| `make docker-build` / `docker-run` / `docker` | Image build/run. |
| `make clean` | Remove caches, `.venv`, coverage outputs. |

`mypy` runs in **strict** mode (`[tool.mypy] strict = true` in `pyproject.toml`)
with the django-stubs plugin. `bandit` runs with the skip list in
`[tool.bandit]`. Pre-commit hooks are installed by `make install`.

### GitHub Actions

- **`lint_and_test.yaml`** — on PR to `main`/`release`: checkout, install uv,
  `uv sync --frozen`, `make all`, `make audit` (Postgres 17 service, gettext).
- **`docker.yaml`** — on PR to `main` (unsigned PR image) and on `vX.Y.Z` /
  `vX.Y.Z-rc.N` tags (pushed + cosign-signed for non-RC releases) via
  `docker/build-push-action` to `ghcr.io`.
- **`semantic.yaml`** — semantic-release via `ghcr.io/disafronov/semantic-release`;
  dry-run validation on PR, release on push to `main`/`release`, and a sync of
  `release` → `main`.
- **`auto-pr-description.yml`** — on PR to `release`: auto-generates the PR
  description/title (release PRs).

## Project layout

- `sopds/` — Django project package: `settings.py`, `urls.py`, `wsgi.py`, `locale/`.
- `opds_catalog/` — core app: models, scanner (`sopdscan`), OPDS feed generation,
  middleware, fixtures, and the `sopds_scanner` / `sopds_server` / `sopds_util` /
  `sopds_telebot` management commands.
- `sopds_web_backend/` — web UI app: views, templates, admin, static assets,
  and its own settings knobs (e.g. `HALF_PAGES_LINKS`).
- `ops/` — operations app: `dev` and `start` launchers, process supervisor
  (`supervisor.py`), `health` checks.
- `book_tools/` — book conversion/processing helpers.
- `convert/` — bundled fb2→epub / fb2→mobi converter sources.
- `assets/`, `static/` — front-end assets and collected static files.

## Legacy documentation

The original SimpleOPDS README described OPDS as a catalog protocol for e-book
libraries and the distinction between the HTTP browsing UI and the OPDS feed.
That conceptual framing still applies: SOPDS exposes the same collection at
`/opds/` (machine-readable OPDS 1.2) and `/` (human browsing UI). Historical
setup details (Python 3.4, Django 1.10, `requirements.txt`, MySQL/MyISAM
instructions, `sopds.ru` downloads, built-in `sopds_server` on port 8001 as the
primary server) are obsolete and have been removed.

---

> WIP draft — reflects the repository state as of `main` @ `18b09ff`. Some
> sections (e.g. the CI `DATABASE_URL` gap noted above) need confirmation before
> this becomes the canonical README.
