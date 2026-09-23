# Electricity Bill Splitter — Web App Spec

## Project Goal
A simple local web dashboard to update, manage, and split the electricity bill among flatmates. Data is stored in Excel for now (Supabase later). Single-user for now (login later).

## Business Rules (confirmed)
1. **Per-unit rate** = `monthly_bill_amount / total_units_consumed`
2. **DG bill** split equally among active roommates.
3. **Common units** = `total_main_meter_units - sum(individual_submeter_units)`
   - The leftover is split equally among active roommates.
4. Roommates can change month-to-month (someone can leave / join).
5. One flat with 4 rooms, each room has its own sub-meter.
6. Dashboard must allow entering:
   - Monthly main bill amount
   - DG bill amount
   - Per-room current meter readings
   - Per-person recharges/payments
7. Dashboard must display:
   - Current month bill split
   - Running balances (who owes / who is owed)
   - History of past months
   - Recharge log
8. Distribution = downloadable Excel report only.
9. Database = Excel for now; later Supabase.
10. Auth = single-user for now; later multi-user login.

## Formula Summary
```
monthly_bill        = user input
main_reading_end    = user input
main_reading_start  = previous month main_reading_end OR user input
main_units          = main_reading_end - main_reading_start

for each active roommate:
  sub_units_i       = current_reading_i - previous_reading_i
common_units        = main_units - sum(sub_units_i)
common_share        = common_units / count(active_roommates)
total_units_i       = sub_units_i + common_share
rate                = monthly_bill / main_units
energy_charge_i     = total_units_i * rate
dg_share_i          = dg_bill / count(active_roommates)
total_bill_i        = energy_charge_i + dg_share_i
balance_i           = total_bill_i - recharges_received_i
```

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, Uvicorn, Pandas, OpenPyXL
- **Frontend**: React 18, Vite, Tailwind CSS, Axios (or fetch)
- **Storage**: Excel workbook `data/bills.xlsx` (structured DB sheets)
- **Export**: Human-readable Excel report `exports/{month}_report.xlsx`

## Data Model (Excel sheets)
1. `roommates` — name, join_date, leave_date, is_active
2. `months` — month (YYYY-MM), main_start_reading, main_end_reading, monthly_bill, dg_bill, notes
3. `readings` — month, roommate, current_reading
4. `recharges` — date, roommate, amount, notes

## API Endpoints (FastAPI)
- `GET /api/roommates`
- `POST /api/roommates`
- `PUT /api/roommates/{id}`
- `GET /api/months`
- `GET /api/months/{month}`
- `POST /api/months`
- `PUT /api/months/{month}`
- `GET /api/calculate/{month}` → returns full split + balances
- `GET /api/history`
- `GET /api/export/{month}` → returns path to generated Excel report

## Frontend Pages / Components
1. **Dashboard**
   - Month selector
   - Current month summary cards
   - Readings input table
   - Recharges input table
   - Bill split table (auto-calculated)
   - Running balances list
2. **History**
   - List of all months with totals
3. **Export**
   - Download report Excel for selected month

## File Structure
```
Electricity_bill_dist/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── db.py
│   │   ├── models.py
│   │   ├── calc.py
│   │   └── export.py
│   ├── data/
│   │   └── bills.xlsx
│   ├── exports/
│   ├── requirements.txt
│   └── README.md
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   ├── pages/
│   │   └── api.js
│   ├── index.html
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.js
├── SPEC.md
└── README.md
```

## Migration
Import historical data from `C:\Users\goran\Downloads\electricity golf 1.xlsx` into `backend/data/bills.xlsx` using the structured sheets above. Because names and roommates change, we will import each month with its active roommate set.

## Notes
- CORS must be enabled on the backend for the Vite dev server.
- Use React functional components + hooks; Tailwind for styling.
- Keep the UI simple and clean (single page is fine).
