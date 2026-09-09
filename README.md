# Utilități.MD

Web app for tracking Moldova utility bills (energy, water, internet, sanitation)
across multiple homes: it extracts invoices, notifies people when a new invoice
arrives, and monitors its payment status. FastAPI + Jinja2 + SQLite, with
provider connectors in the bundled `pyutilitati_md` library.

Invoices are verified through **oplata.md**: Premier Energy, Energocom,
Moldovagaz, INFOCOM, Termoelectrica, Apă-Canal Chișinău, StarNet, FEE Nord,
Stroy Master Domofon (via the generic oplata connector) and InfoSapr (dedicated
connector, oplata service id `602`).

### oplata.md service ids

Each generic provider carries its oplata.md **service id** as a constant in code
(`pyutilitati_md/providers/oplata_utility.py`, `OPLATA_SERVICE_IDS`). This is the
numeric `Id` oplata.md uses to route the `/payment/check` request to the right
provider. Confirmed service ids (as of Aug 2026): Premier Energy `604`,
Energocom `1333`, Moldovagaz `603`, Termoelectrica `815`, Apă-Canal Chișinău
`605`, StarNet `300`, FEE Nord `1184`, InfoSapr `602`. `INFOCOM` and
`Stroy Master Domofon` are still `0` — set their oplata.md service id in code
before deploying them.

## Run with Docker

Imaginea NU se mai compilează local — GitHub Actions o construiește și o
publică automat pe GHCR (`.github/workflows/build-docker.yml`). `compose.yaml`
trage mereu build-ul publicat (`pull_policy: always`):

```bash
cp .env.example .env      # then edit secrets
docker compose up -d
```

Build-ul folosit este cel al ramurii `deploy` (`ghcr.io/vadikonline1/utilitati_md:deploy`).
Pentru a alege alt build (ex. `main`, un SHA):

```bash
IMAGE_TAG=main docker compose up -d
```

Pachetele GHCR sunt **private** implicit — pe server autentifică-te o dată cu un
PAT cu scope `read:packages`:

```bash
echo "$PAT" | docker login ghcr.io -u vadikonline1 --password-stdin
```

Open http://localhost:8000 — the default login is `admin` / `admin` (from
`UTILITATI_USERNAME` / `UTILITATI_PASSWORD`; change it in `.env`).

The SQLite database persists in the `utilitati-data` volume (`/app/data` inside
the container).

### Docker image (GitHub Actions)

Workflow-ul `.github/workflows/build-docker.yml` construiește imaginea și o
publică, la fiecare push pe `main` / `deploy`, în GitHub Container Registry:
`ghcr.io/vadikonline1/utilitati_md:<ramură>`, `:<sha>` și `:latest`. Pentru a
rula instructiunea publicată în loc de build local:

```bash
docker pull ghcr.io/vadikonline1/utilitati_md:latest
docker compose up -d
```

Imaginea expune același `GIT_SHA` (build arg) pe care îl afișează admin-panel-ul.

## Configuration (environment variables)

| Variable                  | Default                 | Description                    |
| ------------------------- | ----------------------- | ------------------------------ |
| `UTILITATI_SECRET_KEY`    | `change-me-in-production`| HMAC key for session tokens   |
| `UTILITATI_USERNAME`      | `admin`                 | Default admin username         |
| `UTILITATI_PASSWORD`      | `admin`                 | Default admin password         |
| `UTILITATI_DB`            | `./utilitati.db`        | SQLite database path           |
| `SMTP_HOST` / `SMTP_PORT` | _(unset)_              | Mail server for notifications  |
| `SMTP_USER` / `SMTP_PASS` | _(unset)_              | SMTP login (password hidden in UI) |
| `SMTP_FROM`               | _(unset)_              | Sender address                 |
| `TELEGRAM_TOKEN`          | _(unset)_              | Telegram bot token (hidden in UI) |
| `TELEGRAM_BOTNAME`        | _(unset)_              | Telegram bot short name        |
| `ADMOB_ID_BANNER`         | _(unset)_              | Banner ad unit id (read-only in UI) |
| `ADMOB_ID_INTERSTITIAL`   | _(unset)_              | Interstitial ad unit id (read-only in UI) |
| `ADMOB_ID_REWARDED`       | _(unset)_              | Rewarded ad unit id (read-only in UI) |

> SMTP/Telegram credentials can be set either in `/admin` (stored encrypted in
> the database) or via the environment variables above. Env takes precedence and
> the fields are shown masked (never in plaintext) in the admin panel.

## Run locally (dev)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py                 # uvicorn on 0.0.0.0:8000
```
