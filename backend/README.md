# HeatShield API

## Start backend
```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Open API docs at http://localhost:8000/docs

## Authentication and authorization

All operational `/api/*` endpoints require a signed bearer token. The backend re-checks account activation and the current role on protected requests. Sign in at `POST /api/auth/login` and send the returned token as `Authorization: Bearer <token>`. The first administrator is bootstrapped only when the user table is empty; an existing database administrator password is never overwritten by bootstrap settings. Configure a private `HEATSHIELD_AUTH_SECRET` and exact `HEATSHIELD_CORS_ORIGINS` before deployment. The current role matrix is a prototype baseline and does not yet provide complete per-worksite isolation.

## Endpoints
- `GET /api/health`
- `GET /api/cities`
- `GET /api/weather/islamabad`
- `GET /api/weather/lahore`
- `GET /api/weather/karachi`
- `GET /api/weather/multan`
- `GET /api/weather/peshawar`
- `GET /api/weather/quetta`
- `GET /api/weather/faisalabad`
- `GET /api/weather/abu_dhabi`
- `GET /api/weather/dubai`
- `GET /api/weather/sharjah`
- `GET /api/weather/al_ain`

Weather source: Open-Meteo Forecast API. Attribution is required (CC BY 4.0).


## Worksite management API (v0.3)

The backend now includes a local SQLite database for worksite records. The database file is created automatically at `backend/heatshield.db` on first startup.

Available endpoints:
- `GET /api/worksites` — list worksites
- `POST /api/worksites` — create a worksite
- `PUT /api/worksites/{worksite_id}` — update a worksite
- `DELETE /api/worksites/{worksite_id}` — delete a worksite

Example JSON for `POST /api/worksites`:

```json
{
  "name": "North Warehouse",
  "city": "Islamabad",
  "industry": "Logistics",
  "worker_count": 24
}
```

Open `http://localhost:8000/docs` and try the endpoints. Records persist locally in SQLite between backend restarts. This is a development database. Authentication and baseline role checks are implemented, but production multi-user deployment still requires per-worksite authorization, secure cookie sessions, audit logging, backup/restore procedures and managed schema migrations.

## Global medical and occupational knowledge library

A separate, source-governed knowledge ingestion package is available under `app/knowledge/`. It does not replace the existing BioTwin research assistant.

See [`app/knowledge/README.md`](app/knowledge/README.md) for the source registry, rights controls, supported document formats, and ingestion instructions. The initial registry is in `data/knowledge/source_registry.json`.

From the `backend/` directory, run:

```powershell
python -m app.knowledge.ingest
```

Only locally supplied documents whose registry record has `ingestion_approved: true` are processed. Rights review is never bypassed by `--force`.
