# Utilități.MD

Web app for tracking Moldova utility bills (energy, water, internet, sanitation)
across multiple homes: it extracts invoices, notifies people when a new invoice
arrives, and monitors its payment status. FastAPI + Jinja2 + SQLite, with
provider connectors in the bundled `pyutilitati_md` library.

All providers are verified through **oplata.md** only: Premier Energy,
Energocom, Termoelectrica, INFOCOM, FEE Nord, Apă-Canal Chișinău, Stroy Master
Domofon, StarNet, InfoSapr and Auto Salubritate.

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

### oplata.md service ids

Each provider carries its oplata.md **service id** as a constant in code
(`pyutilitati_md/providers/oplata_utility.py`, `OPLATA_SERVICE_IDS`). Set the
correct oplata.md service id for the providers you deploy directly in code — no
environment configuration is required. InfoSapr and Auto Salubritate use their
own dedicated connectors with verified ids hardcoded (InfoSapr `602`, Auto
Salubritate `606`). Each user simply enters their own account reference in the
app (Cod NLC, Numărul contului, Codul personal, Numărul contractului, Cont
Abonat, etc.).

## Run locally (dev)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                 # uvicorn on 0.0.0.0:8000
```
