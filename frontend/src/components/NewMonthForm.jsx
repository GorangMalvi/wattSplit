import { useState } from 'react';
import { formatMoney, meterBill } from '../format';
import MeterBalanceFields from './MeterBalanceFields';

// Month after the latest stored one, or the current month when there are none.
function suggestMonth(months) {
  if (months.length === 0) return new Date().toISOString().slice(0, 7);
  const latest = [...months].map((m) => m.month).sort().at(-1);
  const [year, mon] = latest.split('-').map(Number);
  return mon === 12 ? `${year + 1}-01` : `${year}-${String(mon + 1).padStart(2, '0')}`;
}

function NewMonthForm({ months, onCreate, onCancel, loading }) {
  const isFirst = months.length === 0;
  const latest = [...months].sort((a, b) => (a.month < b.month ? 1 : -1))[0];
  const [form, setForm] = useState({
    month: suggestMonth(months),
    monthly_bill: '',
    dg_bill: '',
    main_start_reading: '',
    main_end_reading: '',
    // The meter's balance carries over: last month's closing is this month's opening.
    meter_opening_balance: latest?.meter_closing_balance ?? '',
    meter_recharge: '',
    meter_closing_balance: '',
  });

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });
  const num = (value) => (value === '' ? null : parseFloat(value));
  const bill = meterBill(form.meter_opening_balance, form.meter_recharge, form.meter_closing_balance);

  const handleSubmit = (e) => {
    e.preventDefault();
    onCreate({
      month: form.month,
      // A negative bill (closing too high) is left for the backend to explain.
      monthly_bill: bill !== null && bill >= 0 ? bill : num(form.monthly_bill) ?? 0,
      dg_bill: num(form.dg_bill) ?? 0,
      // Blank start reading = carried over from the previous month's end reading.
      main_start_reading: num(form.main_start_reading),
      main_end_reading: num(form.main_end_reading),
      meter_opening_balance: num(form.meter_opening_balance),
      meter_recharge: num(form.meter_recharge),
      meter_closing_balance: num(form.meter_closing_balance),
    });
  };

  return (
    <form onSubmit={handleSubmit} className="card">
      <h2 className="mb-4 text-lg font-semibold text-slate-900">New Month</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-slate-500">Month</label>
          <input type="month" required value={form.month} onChange={set('month')} />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-slate-500">Main Start Reading</label>
          <input
            type="number"
            step="0.01"
            min="0"
            placeholder={isFirst ? '0' : 'Previous month’s end'}
            value={form.main_start_reading}
            onChange={set('main_start_reading')}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-slate-500">Main End Reading</label>
          <input
            type="number"
            step="0.01"
            min="0"
            value={form.main_end_reading}
            onChange={set('main_end_reading')}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-slate-500">Monthly Bill (amount deducted)</label>
          <input
            type="number"
            step="0.01"
            min="0"
            value={bill ?? form.monthly_bill}
            readOnly={bill !== null}
            title={bill !== null ? 'Worked out from the meter balances below' : undefined}
            className={bill !== null ? 'bg-slate-50' : ''}
            onChange={set('monthly_bill')}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-slate-500">DG Bill</label>
          <input
            type="number"
            step="0.01"
            min="0"
            value={form.dg_bill}
            onChange={set('dg_bill')}
          />
        </div>
      </div>
      <MeterBalanceFields
        opening={form.meter_opening_balance}
        recharge={form.meter_recharge}
        closing={form.meter_closing_balance}
        onChange={(field, value) => setForm({ ...form, [field]: value })}
        idPrefix="new-month"
        openingHint={latest?.meter_closing_balance != null ? `${formatMoney(latest.meter_closing_balance)} carried from ${latest.month}` : null}
      />
      <div className="mt-4 flex items-center gap-3">
        <button type="submit" disabled={loading || !form.month} className="btn-primary">
          Create Month
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="btn-secondary">
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

export default NewMonthForm;
