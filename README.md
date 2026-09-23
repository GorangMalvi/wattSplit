# Electricity Bill Splitter

A simple local web dashboard to manage and split the electricity bill among flatmates.

## Stack
- **Backend**: Python 3.11+, FastAPI, OpenPyXL, Pandas
- **Frontend**: React 18, Vite, Tailwind CSS
- **Storage**: Excel workbook (`backend/data/bills.xlsx`) — Supabase later

## Quick Start

### 1. Start the backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Backend runs at `http://localhost:8000`.

### 2. Start the frontend
```bash
cd frontend
npm install
npm run dev
```
Frontend runs at `http://localhost:5173`.

## Run with Docker
```bash
docker compose up -d --build
```
Open **http://wattsplit.localhost** (also available at `http://localhost:5173`).
The URL/port are set in `.env` (`LOCAL_HOST_URL`, `LOCAL_HOST_PORT`).

## Features
- Add/edit monthly meter readings
- Record recharges/payments by person
- Auto-calculate bill split including common units and DG charges
- Running balances
- Download monthly Excel report

## Project Structure
```
Electricity_bill_dist/
├── backend/        # FastAPI + Excel storage
├── frontend/       # React + Tailwind dashboard
├── SPEC.md         # Full specification
└── README.md       # This file
```

## Notes
- Historical data was imported from `C:\Users\goran\Downloads\electricity golf 1.xlsx`.
- Single-user mode for now; multi-user login and Supabase integration planned later.
