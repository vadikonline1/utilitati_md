FROM python:3.12-slim

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

RUN mkdir -p /app/data

EXPOSE 8000

# Persist the SQLite database in a volume-friendly location.
ENV UTILITATI_DB=/app/data/utilitati.db

# Non-root user for better isolation.
RUN useradd -ms /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
