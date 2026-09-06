FROM python:3.12-slim

ARG GIT_SHA=unknown
ENV GIT_SHA=$GIT_SHA

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System build deps for aiohttp wheels (greenlet, etc.).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .
COPY entrypoint.sh /entrypoint.sh

RUN mkdir -p /app/data

EXPOSE 8000

# Persist the SQLite database in a volume-friendly location.
ENV UTILITATI_DB=/app/data/utilitati.db

# Non-root user for better isolation. The entrypoint (as root) fixes ownership
# of the mounted data dir on startup, then drops privileges to appuser.
RUN useradd -ms /bin/bash appuser \
    && chown -R appuser:appuser /app \
    && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
