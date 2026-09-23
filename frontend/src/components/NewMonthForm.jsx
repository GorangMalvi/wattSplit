import { useState } from 'react';

// Month after the latest stored one, or the current month when there are none.
function suggestMonth(months) {
  if (months.length === 0) return new Date().toISOString().slice(0, 7);
  const latest = [...months].map((m) => m.month).sort().at(-1);
  const [year, mon] = latest.split('-').map(Number);
  return mon === 12 ? `${year + 1}-01` : `${year}-${String(mon + 1).padStart(2, '0')}`;
}

function NewMonthForm({ months, onCreate, onCancel, loading }) {
  const isFirst = months.length === 0;
  const [form, setForm] = useState({
    month: suggestMonth(months),
    monthly_bill: '',
    dg_bill: '',
    main_start_reading: '',
    main_end_reading: '',
  });

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });
  const num = (value) => (value === '' ? null : parseFloat(value));

  const handleSubmit = (e) => {
    e.preventDefault();
    onCreate({
      month: form.month,
      monthly_bill: num(form.monthly_bill) ?? 0,
      dg_bill: num(form.dg_bill) ?? 0,
      // Blank start reading = carried over from the previous month's end reading.
      main_start_reading: num(form.main_start_reading),
      main_end_reading: num(form.main_end_reading),
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
          <label className="text-xs font-medium text-slate-500">Monthly Bill</label>
          <input
            type="number"
            step="0.01"
            min="0"
            value={form.monthly_bill}
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
