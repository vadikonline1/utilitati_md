# Utilități.MD

Web app for tracking Moldova utility bills (energy, water, internet, sanitation)
across multiple homes. FastAPI + Jinja2 + SQLite, with provider connectors in the
bundled `pyutilitati_md` library (Premier Energy, InfoSapr, Energocom, StarNet,
FEE Nord, Apă-Canal Chișinău, Auto Salubritate, Termoelectrica, INFOCOM,
Stroy Master Domofon).

## Run with Docker

```bash
cp .env.example .env      # then edit secrets
docker compose up -d --build
```

Open http://localhost:8000 — the default login is `admin` / `admin` (from
`UTILITATI_USERNAME` / `UTILITATI_PASSWORD`; change it in `.env`).

The SQLite database persists in the `utilitati-data` volume (`/app/data` inside
the container).

## Configuration (environment variables)

| Variable                  | Default                 | Description                    |
| ------------------------- | ----------------------- | ------------------------------ |
| `UTILITATI_SECRET_KEY`    | `change-me-in-production`| HMAC key for session tokens   |
| `UTILITATI_USERNAME`      | `admin`                 | Default admin username         |
| `UTILITATI_PASSWORD`      | `admin`                 | Default admin password         |
| `UTILITATI_DB`            | `./utilitati.db`        | SQLite database path           |

## Run locally (dev)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                 # uvicorn on 0.0.0.0:8000
```
