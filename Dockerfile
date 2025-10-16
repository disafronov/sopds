FROM python:3.7-slim AS base
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PATH="/opt/sopds/bin:$PATH"
WORKDIR /home/sopds
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
    rm -rf /var/lib/apt/lists/* && \
    python3 -m venv /opt/sopds
COPY requirements.txt requirements-override.txt /home/sopds/
RUN pip3 install --ignore-installed --no-cache-dir --upgrade --disable-pip-version-check pip setuptools wheel && \
    pip3 install --ignore-installed --no-cache-dir -r requirements.txt -r requirements-override.txt

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
ENTRYPOINT [ "/home/sopds/entrypoint.sh" ]
CMD [ "help" ]
USER sopds:sopds
