# wattSplit

Split a shared flat's electricity bill fairly from sub-meter readings, common units and DG charges. Track recharges and running balances, and export monthly Excel reports.

## Stack
- **Backend**: Python 3.11+, FastAPI, Pandas, OpenPyXL, psycopg
- **Frontend**: React, Vite, Tailwind CSS, supabase-js
- **Auth & storage**: Supabase (email one-time-code login, Postgres)

## How it works
- Users sign in with a one-time code emailed by Supabase Auth (no passwords; the account is created on first sign-in). Each user creates a **household** (a flat) or joins one with its 8-character invite code; all roommates, months, readings and recharges belong to a household.
- The frontend sends the Supabase access token and the chosen household (`X-Household-Id`) with every API call. FastAPI verifies the token and checks membership before touching any data.
- Tables have Row Level Security enabled, so the public anon key cannot read another household's data through Supabase's REST API.

## Supabase setup (once)
1. Copy `.env.example` to `.env` and fill in, from your Supabase project:
   - `SUPABASE_URL` and `SUPABASE_ANON_KEY`: **Project Settings → API**
   - `DATABASE_URL`: **Connect → Session pooler** connection string, with your database password filled in
   - `SUPABASE_JWT_SECRET`: only if the project still uses the legacy JWT secret; leave it empty for JWT signing keys
2. Create the tables (safe to re-run after schema changes):
   ```bash
   cd backend
   pip install -r requirements.txt
   python -m app.init_schema
   ```
   Or paste `backend/app/schema.sql` into the Supabase SQL editor.
3. Send sign-in codes through Mailtrap. Supabase's built-in email can't use custom templates on the free plan, so Mailtrap is set as the project's SMTP provider:
   - In Mailtrap, add and verify a sending domain (or use the demo domain for testing), then copy its API token.
   - Fill `MAILTRAP_API_TOKEN`, `MAIL_FROM_EMAIL`, `MAIL_FROM_NAME` and `SUPABASE_ACCESS_TOKEN` in `.env`.
   - Run:
     ```bash
     cd backend
     python -m app.mailer you@example.com   # test email via the Mailtrap SDK
     python -m app.setup_auth_email         # Mailtrap SMTP + code templates in Supabase
     ```
   - Remove `SUPABASE_ACCESS_TOKEN` from `.env` and revoke it afterwards.
   - Sent emails show up at https://mailtrap.io/sending/email_logs

`.env` is git-ignored because `DATABASE_URL` contains your database password. Never commit it.

## Run with Docker
```bash
docker compose up -d --build
```
Open **http://wattsplit.localhost** (also available at `http://localhost:5173`).
The URL and port are set in `.env` (`LOCAL_HOST_URL`, `LOCAL_HOST_PORT`).

## Run locally without Docker
```bash
# Backend (reads the repo-root .env)
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend, in another terminal (proxies /api to the backend)
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173`.

## Android app (APK)
The React app is wrapped with [Capacitor](https://capacitorjs.com/) (`frontend/android/`). The APK can't use the local `/api` proxy, so it calls a **deployed** backend.

### 1. Deploy the backend (Render, free)
1. On [render.com](https://render.com), **New → Blueprint**, connect this GitHub repo. It reads `render.yaml`.
2. Enter the secrets it asks for: `SUPABASE_URL`, `DATABASE_URL` (Session pooler), `MAILTRAP_API_TOKEN`, `MAIL_FROM_EMAIL`. Leave `SUPABASE_JWT_SECRET` empty for JWT signing keys.
3. When it's live, check `https://<your-service>.onrender.com/api/health` returns `{"status":"ok"}`.

The free plan sleeps after 15 minutes idle; the first request after that takes up to a minute.

### 2. Build the APK
Needs JDK 21 and the Android SDK (platform 35) with `JAVA_HOME` and `ANDROID_HOME` set.
```bash
# .env: MOBILE_API_URL=https://<your-service>.onrender.com/api
cd frontend
npm install
npm run apk
```
The APK is written to `frontend/android/app/build/outputs/apk/debug/app-debug.apk`. Copy it to the phone and open it (allow "install unknown apps" for the file manager / browser you open it with).

## Features
- Passwordless sign-in with an emailed one-time code; households with invite codes
- Manage roommates (join/leave months, active flag)
- Create months; the main meter start reading carries over from the previous month
- Enter per-room meter readings and recharges/payments
- Auto-calculate the split, including common units and DG charges
- Running balances
- Download a monthly Excel report

## Project Structure
```
Electricity_bill_dist/
├── backend/
│   └── app/
│       ├── main.py         # API routes
│       ├── auth.py         # Supabase token verification
│       ├── db.py           # Postgres access, household-scoped
│       ├── calc.py         # Bill split math
│       ├── export.py       # Excel report
│       ├── schema.sql      # Tables + RLS policies
│       └── init_schema.py  # Applies schema.sql
├── frontend/               # React + Tailwind dashboard
├── .env.example            # Settings template
├── SPEC.md                 # Business rules and formulas
└── README.md
```
