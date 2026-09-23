# Electricity Bill Splitter — Frontend

A single-page React dashboard for managing electricity bill splits among flatmates.

## Tech Stack

- React 18/19 + Vite
- Tailwind CSS v3
- Axios

## Getting Started

1. Install dependencies:
   ```bash
   npm install
   ```

2. Start the Vite dev server:
   ```bash
   npm run dev
   ```
   The app will be available at `http://localhost:5173` (or the next free port).

3. Make sure the backend is running at `http://localhost:8000` with CORS enabled.

4. To create a production build:
   ```bash
   npm run build
   ```

## Environment Variables

You can override the backend URL by creating a `.env` file in this directory:

```env
VITE_API_URL=http://localhost:8000/api
```

If not set, the frontend defaults to `http://localhost:8000/api`.

## Project Structure

```
frontend/
├── public/
├── src/
│   ├── api.js                # Axios instance and API helper functions
│   ├── App.jsx               # Main dashboard page
│   ├── components/
│   │   ├── BalanceCard.jsx
│   │   ├── BillSplitTable.jsx
│   │   ├── ErrorAlert.jsx
│   │   ├── LoadingSpinner.jsx
│   │   ├── MonthSelector.jsx
│   │   ├── ReadingsTable.jsx
│   │   ├── RechargesTable.jsx
│   │   └── SummaryCard.jsx
│   ├── index.css             # Tailwind directives + custom component classes
│   └── main.jsx
├── index.html
├── package.json
├── postcss.config.js
├── tailwind.config.js
└── vite.config.js
```
