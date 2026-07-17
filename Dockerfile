# syntax = docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.11.29 AS uv

FROM ubuntu:noble-20260610 AS base

# ENVs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC

# Base dependencies (runtime libraries required by sopds)
ARG BASE_DEPENDENCIES="libpq5 libmariadb3 libxml2 libxslt1.1 libffi8 libjpeg62-turbo zlib1g xz-utils bzip2 unzip"
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

# Build dependencies required to compile C extensions (mysqlclient, psycopg, lxml).
# Git is also required for dependencies installed directly from Git repositories.
USER root
ARG BUILD_DEPENDENCIES="pkg-config build-essential libmariadb-dev libpq-dev libxml2-dev libxslt-dev libffi-dev libjpeg-dev zlib1g-dev liblzma-dev libbz2-dev"
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
    uv sync --frozen --no-install-project --link-mode=copy --no-editable --group docker

# Copy the project into the image — no src/, files are at root.
COPY --chown=ubuntu:ubuntu \
    ./ /home/ubuntu/app/

# Sync the project now that sources exist.
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=type=cache,target=/home/ubuntu/.cache/uv,uid=1000,gid=1000 \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --link-mode=copy --no-editable --group docker

##########################

FROM base AS runtime

# Copy venv and app files from builder stage.
COPY --from=builder /home/ubuntu/.local/.venv/ /home/ubuntu/.local/.venv/
COPY --from=builder /home/ubuntu/app/ /home/ubuntu/app/

WORKDIR /home/ubuntu/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000', timeout=3).read()"]

# sopds orchestrates startup via entrypoint.sh (links /srv/settings.py, runs migrate).
COPY --chown=ubuntu:ubuntu entrypoint.sh /home/ubuntu/app/entrypoint.sh
RUN chmod a+x /home/ubuntu/app/entrypoint.sh

VOLUME ["/srv"]
ENTRYPOINT ["/home/ubuntu/app/entrypoint.sh"]
CMD ["help"]
USER ubuntu:ubuntu
