# wattSplit — Backend

FastAPI backend for wattSplit, using Supabase for auth and Postgres storage.
See the root `README.md` for Supabase setup and running with Docker.

## Stack

- Python 3.11+
- FastAPI + Uvicorn
- psycopg 3 (connection pool) against Supabase Postgres
- PyJWT to verify Supabase access tokens
- Pandas + OpenPyXL for the split calculation and Excel report

## Project layout

```
backend/
├── app/
│   ├── __init__.py     # Loads the repo-root .env for local runs
│   ├── main.py         # FastAPI app and endpoints
│   ├── auth.py         # Supabase JWT verification
│   ├── db.py           # Household-scoped Postgres queries + HouseholdData snapshot
│   ├── models.py       # Pydantic models
│   ├── calc.py         # Bill-splitting calculation
│   ├── export.py       # Excel report generator
│   ├── schema.sql      # Tables, indexes, RLS policies
│   └── init_schema.py  # python -m app.init_schema
├── requirements.txt
└── README.md
```

## Setup

```bash
python -m venv venv
venv\Scripts\activate   # Windows
pip install -r requirements.txt
python -m app.init_schema   # creates/updates tables in Supabase
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Settings come from the repo-root `.env` (see `.env.example`): `SUPABASE_URL`,
`DATABASE_URL`, and `SUPABASE_JWT_SECRET` for legacy-secret projects only.

Interactive docs: `http://127.0.0.1:8000/docs`.

## Auth

Every route except `/api/health` needs `Authorization: Bearer <Supabase access token>`.
Data routes also need `X-Household-Id: <uuid>` for a household the user belongs to;
other households return `403`.

## API endpoints

- `GET /api/health`
- `GET /api/households`, `POST /api/households`, `POST /api/households/join`
- `GET /api/roommates`, `POST /api/roommates`, `PUT /api/roommates/{id}`
- `GET /api/months`, `GET /api/months/{month}`, `POST /api/months`, `PUT /api/months/{month}`
- `PUT /api/readings/{month}/{roommate_id}`
- `GET /api/recharges?month=`, `POST /api/recharges`, `PUT /api/recharges/{id}`, `DELETE /api/recharges/{id}`
- `GET /api/calculate/{month}`
- `GET /api/history`
- `GET /api/export/{month}` (downloads `{month}_report.xlsx`)

`{month}` is always `YYYY-MM` (e.g. `2025-09`).
