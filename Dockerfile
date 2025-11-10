# syntax = docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:0.9.8 AS uv

FROM python:3.8-slim AS base
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PATH="/opt/sopds/bin:$PATH"
ARG BASE_DEPENDENCIES="libpq5 libmariadb3 libxml2 libxslt1.1 libffi8 libjpeg62-turbo zlib1g xz-utils bzip2"
RUN apt-get update && \
    apt-get install --no-install-recommends -y ${BASE_DEPENDENCIES} && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

############################################################

FROM base AS builder
ARG BUILD_DEPENDENCIES="pkg-config build-essential libmariadb-dev libpq-dev libxml2-dev libxslt-dev libffi-dev libjpeg-dev zlib1g-dev liblzma-dev libbz2-dev"
RUN apt-get update && \
    apt-get install --no-install-recommends -y ${BUILD_DEPENDENCIES} && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=type=bind,source=.python-version,target=.python-version \
    uv venv /opt/sopds
WORKDIR /home/sopds
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=.python-version,target=.python-version \
    uv sync --no-cache --no-dev --extra docker

############################################################

FROM base AS runtime
ARG RUNTIME_DEPENDENCIES="unzip"
RUN apt-get update && \
    apt-get install --no-install-recommends -y ${RUNTIME_DEPENDENCIES} && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
ARG OWNER_UID=1000 \
    OWNER_GID=1000
RUN ( addgroup --system --gid $OWNER_GID sopds || echo sopds:x:$OWNER_GID:sopds | tee -a /etc/group ) && \
    ( adduser --system --home /home/sopds --ingroup sopds --uid $OWNER_UID sopds --shell /bin/sh || echo sopds:x:$OWNER_UID:$OWNER_GID:Linux User,,,:/home/sopds:/bin/sh | tee -a /etc/passwd )
COPY --from=builder /opt/sopds/ /opt/sopds/
COPY --chown=sopds:sopds . /home/sopds/
RUN chmod a+x /home/sopds/entrypoint.sh
WORKDIR /home/sopds
VOLUME ["/srv"]
ENTRYPOINT [ "/home/sopds/entrypoint.sh" ]
CMD [ "help" ]
USER sopds:sopds
