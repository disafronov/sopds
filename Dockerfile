# syntax = docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.11.29 AS uv

FROM ubuntu:noble-20260610 AS base

# ENVs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC

# Base dependencies (runtime libraries required by sopds)
ARG BASE_DEPENDENCIES="libxml2 libxslt1.1 libffi8 libjpeg-turbo8 zlib1g xz-utils bzip2 unzip libmariadb3"
RUN apt-get update && \
    apt-get install -y --no-install-recommends ${BASE_DEPENDENCIES} && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

USER ubuntu:ubuntu
WORKDIR /home/ubuntu/.local

# Create venv (uses .python-version from the build context).
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/home/ubuntu/.cache/uv,uid=1000,gid=1000 \
    --mount=type=bind,source=.python-version,target=.python-version \
    uv venv

ENV PATH="/home/ubuntu/.local/.venv/bin:$PATH"

##########################

FROM base AS builder

# Build dependencies required to compile C extensions (lxml).
# Git is also required for dependencies installed directly from Git repositories.
USER root
ARG BUILD_DEPENDENCIES="pkg-config build-essential gettext libxml2-dev libxslt-dev libffi-dev libjpeg-turbo8-dev zlib1g-dev liblzma-dev libbz2-dev libmariadb-dev"
RUN apt-get update && \
    apt-get install -y --no-install-recommends ${BUILD_DEPENDENCIES} git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
USER ubuntu:ubuntu

# Install dependencies first (without installing the project itself).
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/home/ubuntu/.cache/uv,uid=1000,gid=1000 \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=.python-version,target=.python-version \
    uv sync --frozen --no-install-project --link-mode=copy --no-editable

# Copy the project into the image — no src/, files are at root.
COPY --chown=ubuntu:ubuntu \
    ./ /home/ubuntu/app/

# Sync the project now that sources exist.
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/home/ubuntu/.cache/uv,uid=1000,gid=1000 \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --link-mode=copy --no-editable

WORKDIR /home/ubuntu/app

# Compile translations and collect static assets while build tools are available.
RUN export DJANGO_SECRET_KEY=unsafe-secret-key-for-tooling \
        DATABASE_URL=postgresql://unused:unused@localhost/unused \
        DJANGO_DEBUG=False && \
    python3 manage.py compilemessages && \
    python3 manage.py collectstatic --noinput

##########################

FROM base AS runtime

# Copy venv and app files from builder stage.
COPY --chown=ubuntu:ubuntu --from=builder /home/ubuntu/.local/.venv/ /home/ubuntu/.local/.venv/
COPY --chown=ubuntu:ubuntu --from=builder /home/ubuntu/app/ /home/ubuntu/app/

WORKDIR /home/ubuntu/app

ENV GUNICORN_WORKERS=2
ENV GUNICORN_CMD_ARGS="--control-socket /tmp/gunicorn.ctl --bind 0.0.0.0:8000 --timeout 120 --worker-tmp-dir /tmp --access-logfile - --error-logfile -"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/readiness/', timeout=3).read()"]

VOLUME ["/books"]
ENTRYPOINT ["python3", "manage.py"]
CMD ["start"]
USER ubuntu:ubuntu
