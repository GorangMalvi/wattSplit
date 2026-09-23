# Electricity Bill Splitter — Backend

FastAPI + Excel backend for the flat electricity bill dashboard.

## Stack

- Python 3.11+
- FastAPI + Uvicorn
- Pandas + OpenPyXL

## Project layout

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py       # FastAPI app and endpoints
│   ├── db.py         # Excel read/write helpers
│   ├── models.py     # Pydantic models
│   ├── calc.py       # Bill-splitting calculation
│   ├── export.py     # Excel report generator
│   └── migrate.py    # Historical data importer
├── data/
│   └── bills.xlsx    # Structured database
├── exports/
│   └── {month}_report.xlsx
├── requirements.txt
└── README.md
```

## Setup

1. Open a terminal in `backend/`.
2. (Optional) create a virtual environment:
   ```bash
   python -m venv venv
   venv\Scripts\activate   # Windows
   # source venv/bin/activate  # macOS/Linux
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Run the server

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API is available at `http://127.0.0.1:8000`.
Interactive docs: `http://127.0.0.1:8000/docs`.

CORS is enabled for the Vite dev server at `http://localhost:5173`.

## Migrate historical data

The historical workbook lives at `C:\Users\goran\Downloads\electricity golf 1.xlsx`.
To import it into `backend/data/bills.xlsx`:

```bash
python -m app.migrate
```

This overwrites `bills.xlsx`. The migration creates a base month before the
first billed month so that sub-meter consumption can be calculated from the
imported readings.

## API endpoints

- `GET /api/roommates`
- `POST /api/roommates`
- `PUT /api/roommates/{id}`
- `GET /api/months`
- `GET /api/months/{month}`
- `POST /api/months`
- `PUT /api/months/{month}`
- `POST /api/readings`
- `POST /api/recharges`
- `GET /api/calculate/{month}`
- `GET /api/history`
- `GET /api/export/{month}`

`{month}` is always `YYYY-MM` (e.g. `2025-09`).

## Report export

`GET /api/export/{month}` generates
`backend/exports/{month}_report.xlsx` and returns the file path.

## Migration notes

The historical workbook is messy. The importer (`app/migrate.py`) makes these
assumptions:

- Saksham → Gorang and Vipul → Akash were treated as the same people over time
  (matching the note in the spec).
- Ujjwal is kept as a separate early roommate because the Apr 2025 sheet has
  both Ujjwal and Saksham as distinct rooms.
- The right-hand recharge tables mix carry-forward balances, net-recharge
  totals and actual payments. To avoid double-counting balances as payments,
  only explicit free-form payment entries (`date + amount + name`) and the
  Sheet2 log were imported.
- A synthetic base month (`2025-03`) is created before the first billed month
  so that sub-meter consumption can be calculated from the imported readings.
- Where only a start reading was present for a month, the end reading was
  computed from the per-room sub-units row.
