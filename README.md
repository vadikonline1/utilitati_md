# Utilități.MD

Web app for tracking Moldova utility bills (energy, water, internet, sanitation)
across multiple homes: it extracts invoices, notifies people when a new invoice
arrives, and monitors its payment status. FastAPI + Jinja2 + SQLite, with
provider connectors in the bundled `pyutilitati_md` library.

Invoices are verified through **oplata.md**: Premier Energy, Energocom,
INFOCOM, Termoelectrica, Apă-Canal Chișinău, StarNet, FEE Nord, Stroy Master
Domofon (via the generic oplata connector) and InfoSapr (dedicated connector,
oplata service id `602`).

### oplata.md service ids

Each generic provider carries its oplata.md **service id** as a constant in code
(`pyutilitati_md/providers/oplata_utility.py`, `OPLATA_SERVICE_IDS`). This is the
numeric `Id` oplata.md uses to route the `/payment/check` request to the right
provider. Only FEE Nord's id (`1184`) and InfoSapr's id (`602`) are verified;
set the correct oplata.md service id directly in code for the other providers
you deploy before going live, otherwise oplata.md cannot look up the account.

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
