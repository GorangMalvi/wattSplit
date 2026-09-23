import { useEffect, useMemo, useRef, useState } from 'react';
import {
  createRecharge,
  deleteReading,
  deleteRecharge,
  getMyDashboard,
  linkMyRoommate,
  unlinkMyRoommate,
  updateReading,
} from '../api';
import { formatMoney, formatMonth, formatNumber, today } from '../format';
import BalanceCard from './BalanceCard';
import ErrorAlert from './ErrorAlert';
import LoadingSpinner from './LoadingSpinner';
import MeterBadge, { METERS } from './MeterBadge';
import SummaryCard from './SummaryCard';

// First visit: "which roommate are you?"
function LinkRoommateCard({ roommates, onLinked }) {
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const available = roommates.filter((r) => !r.linked);

  const link = async (payload) => {
    setSaving(true);
    setError(null);
    try {
      onLinked(await linkMyRoommate(payload));
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  };

  return (
    <div className="card mx-auto max-w-xl">
      <h2 className="text-lg font-semibold text-slate-900">Which roommate are you?</h2>
      <p className="mb-4 mt-1 text-sm text-slate-500">
        Link your login to your name to see your own usage and bills, and to submit your meter
        reading and payments.
      </p>
      {error && <ErrorAlert message={error} />}
      {available.length > 0 && (
        <div className="mb-5 flex flex-wrap gap-2">
          {available.map((r) => (
            <button
              key={r.id}
              onClick={() => link({ roommate_id: r.id })}
              disabled={saving}
              className="btn-secondary"
            >
              I'm {r.name}
            </button>
          ))}
        </div>
      )}
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) link({ name: name.trim() });
        }}
      >
        <div className="flex flex-1 flex-col gap-1">
          <label htmlFor="self-name" className="text-xs font-medium text-slate-500">
            {available.length > 0 ? 'Not listed? Add yourself' : 'Add yourself as a roommate'}
          </label>
          <input
            id="self-name"
            placeholder="Your name"
            value={name}
            disabled={saving}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <button type="submit" disabled={saving || !name.trim()} className="btn-primary">
          Add me
        </button>
      </form>
    </div>
  );
}

// Months a roommate can enter a reading for, newest first: the ones they take
// part in, plus any that already have one of their readings.
const readingMonths = (months) =>
  [...months]
    .filter((m) => m.is_active || m.current_reading !== null || m.start_reading !== null)
    .reverse();

const parseReading = (text) => {
  const n = parseFloat(text);
  return Number.isNaN(n) || n < 0 ? null : n;
};

// month/onMonthChange: controlled by the dashboard so "Edit" in the history
// table can pick the month. When there's no reading last month (e.g. your first
// month) the start reading is asked for too, instead of counting the whole meter.
function ReadingForm({ months, month, onMonthChange: setMonth, roommateId, onSaved }) {
  const options = useMemo(() => readingMonths(months), [months]);
  const selected = options.find((m) => m.month === month);
  const [value, setValue] = useState('');
  const [startValue, setStartValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const stored = selected?.current_reading ?? '';
  const storedStart = selected?.start_reading ?? '';
  useEffect(() => {
    setValue(stored);
    setStartValue(storedStart);
    setError(null);
  }, [month, stored, storedStart]);

  if (options.length === 0) {
    return (
      <p className="text-sm text-slate-500">
        No billing months yet. The household owner starts each month.
      </p>
    );
  }

  const askStart = Boolean(selected?.previous_editable);
  const reading = parseReading(value);
  const startReading = askStart ? parseReading(startValue) : null;
  const previous = askStart ? startReading : selected?.previous_reading;
  const units = reading === null ? null : previous == null ? reading : reading - previous;

  // Only what changed: the month-end reading and/or the start reading (blank clears it).
  const changes = {};
  if (reading !== null && reading !== selected?.current_reading) changes.current_reading = reading;
  if (askStart) {
    if (startReading !== null && startReading !== selected?.start_reading) changes.start_reading = startReading;
    if (startValue === '' && selected?.start_reading != null) changes.start_reading = null;
  }
  const canSave = Object.keys(changes).length > 0;

  const save = async (e) => {
    e.preventDefault();
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      await updateReading(month, roommateId, changes);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save} className="space-y-3">
      {error && <ErrorAlert message={error} />}
      <div className={`grid grid-cols-1 gap-3 ${askStart ? 'sm:grid-cols-3' : 'sm:grid-cols-2'}`}>
        <div className="flex flex-col gap-1">
          <label htmlFor="reading-month" className="text-xs font-medium text-slate-500">
            Month
          </label>
          <select id="reading-month" value={month} onChange={(e) => setMonth(e.target.value)}>
            {options.map((m) => (
              <option key={m.month} value={m.month}>
                {formatMonth(m.month)}
                {m.current_reading === null ? ' (reading due)' : ''}
              </option>
            ))}
          </select>
        </div>
        {askStart && (
          <div className="flex flex-col gap-1">
            <label htmlFor="reading-start" className="text-xs font-medium text-slate-500">
              Start reading
            </label>
            <input
              id="reading-start"
              type="number"
              inputMode="decimal"
              step="0.01"
              min="0"
              placeholder="Meter at month start"
              value={startValue}
              onChange={(e) => setStartValue(e.target.value)}
            />
          </div>
        )}
        <div className="flex flex-col gap-1">
          <label htmlFor="reading-value" className="text-xs font-medium text-slate-500">
            {askStart ? 'End reading' : 'Meter reading'}
          </label>
          <input
            id="reading-value"
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0"
            placeholder="e.g. 1234.5"
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        </div>
      </div>
      <p className="text-sm text-slate-500">
        {askStart ? (
          previous == null ? (
            <>No reading last month: enter your meter at the start of this month.</>
          ) : (
            <>
              Start of month: <span className="font-medium">{formatNumber(previous)}</span>
            </>
          )
        ) : (
          <>
            Last reading: <span className="font-medium">{formatNumber(previous)}</span>
          </>
        )}
        {units !== null && (previous != null || !askStart) && (
          <>
            {' '}
            · Units this month:{' '}
            <span className={`font-medium ${units < 0 ? 'text-rose-600' : 'text-slate-800'}`}>
              {formatNumber(units)}
            </span>
          </>
        )}
      </p>
      {units !== null && units < 0 && (
        <p className="text-sm text-rose-600">
          This is lower than the start of the month. Check the meter before saving.
        </p>
      )}
      <button type="submit" disabled={saving || !canSave} className="btn-primary">
        {saving ? 'Saving…' : selected?.current_reading === null ? 'Submit reading' : 'Update reading'}
      </button>
    </form>
  );
}

function PaymentForm({ roommateId, onSaved }) {
  const [date, setDate] = useState(today());
  const [amount, setAmount] = useState('');
  const [notes, setNotes] = useState('');
  const [meter, setMeter] = useState('main');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const value = parseFloat(amount);

  const save = async (e) => {
    e.preventDefault();
    if (Number.isNaN(value) || value <= 0) return;
    setSaving(true);
    setError(null);
    try {
      await createRecharge({ date, roommate_id: roommateId, amount: value, notes, meter });
      setAmount('');
      setNotes('');
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={save} className="space-y-3">
      {error && <ErrorAlert message={error} />}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label htmlFor="pay-date" className="text-xs font-medium text-slate-500">
            Date
          </label>
          <input id="pay-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="pay-amount" className="text-xs font-medium text-slate-500">
            Amount (₹)
          </label>
          <input
            id="pay-amount"
            type="number"
            inputMode="decimal"
            step="0.01"
            min="0"
            placeholder="0.00"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label htmlFor="pay-meter" className="text-xs font-medium text-slate-500">
            Meter
          </label>
          <select id="pay-meter" value={meter} onChange={(e) => setMeter(e.target.value)}>
            {METERS.map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="pay-notes" className="text-xs font-medium text-slate-500">
            Note (optional)
          </label>
          <input
            id="pay-notes"
            placeholder="e.g. UPI to owner"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
      </div>
      <button
        type="submit"
        disabled={saving || !date || Number.isNaN(value) || value <= 0}
        className="btn-primary"
      >
        {saving ? 'Saving…' : 'Add payment'}
      </button>
    </form>
  );
}

// Units per month: own meter plus the share of common units.
function UsageChart({ months }) {
  const bars = months.filter((m) => m.billed || m.sub_units !== null);
  if (bars.length === 0) {
    return <p className="text-sm text-slate-500">Your usage shows up here after your first reading.</p>;
  }
  const units = (m) => (m.billed ? m.total_units : m.sub_units) || 0;
  const max = Math.max(...bars.map(units), 1);
  return (
    <div className="overflow-x-auto">
      <div className="flex h-52 min-w-max items-end gap-3 pb-1">
        {bars.map((m) => (
          <div key={m.month} className="flex w-12 flex-col items-center gap-1">
            <span className="text-xs tabular-nums text-slate-600">{formatNumber(units(m), 0)}</span>
            <div
              className={`w-8 rounded-t-md ${m.billed ? 'bg-indigo-500' : 'bg-indigo-200'}`}
              style={{ height: `${Math.max((units(m) / max) * 140, 2)}px` }}
              title={
                m.billed
                  ? `${formatNumber(m.sub_units)} own + ${formatNumber(m.common_share)} common units`
                  : 'Bill not split yet'
              }
            />
            <span className="text-xs text-slate-500">{formatMonth(m.month)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// active: the tab is showing. Each time it's shown again the data refreshes in
// the background (the Household tab may have changed it) without a spinner.
function MyDashboard({ active = true, roommates, onLinkChange }) {
  const [dash, setDash] = useState(null);
  const [error, setError] = useState(null);
  const [unlinking, setUnlinking] = useState(false);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [readingMonth, setReadingMonth] = useState(null);
  const [confirmDeleteReading, setConfirmDeleteReading] = useState(null);
  const readingCard = useRef(null);

  const load = () =>
    getMyDashboard()
      .then((d) => {
        setDash(d);
        setError(null);
      })
      .catch((err) => setError(err.message));

  useEffect(() => {
    if (active) load();
  }, [active]); // eslint-disable-line react-hooks/exhaustive-deps

  const removePayment = async (id) => {
    try {
      await deleteRecharge(id);
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  const editReading = (month) => {
    setReadingMonth(month);
    readingCard.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const removeReading = async (month) => {
    setConfirmDeleteReading(null);
    try {
      await deleteReading(month, dash.roommate.id);
      await load();
    } catch (err) {
      setError(err.message);
    }
  };

  const unlink = async () => {
    setUnlinking(true);
    try {
      await unlinkMyRoommate();
      onLinkChange(null);
    } catch (err) {
      setError(err.message);
      setUnlinking(false);
    }
  };

  if (error && !dash) return <ErrorAlert message={error} onRetry={load} />;
  if (!dash) return <LoadingSpinner />;

  const { roommate, months } = dash;
  const billed = months.filter((m) => m.billed);
  const latest = billed[billed.length - 1];
  const avgUnits = billed.length
    ? billed.reduce((sum, m) => sum + m.total_units, 0) / billed.length
    : null;
  // Skip months from before joining (or after leaving) that have nothing in them.
  const history = [...months]
    .filter((m) => m.is_active || m.current_reading !== null || m.recharges > 0 || m.billed)
    .reverse();
  const payments = [...dash.recharges].reverse();
  const options = readingMonths(months);
  // Default to the newest month; keep the user's pick while it's still valid.
  const formMonth = options.some((m) => m.month === readingMonth)
    ? readingMonth
    : options[0]?.month || '';

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Hi, {roommate.name}</h2>
          <p className="text-sm text-slate-500">Your electricity usage, bills and payments.</p>
        </div>
        {confirmUnlink ? (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-slate-600">Unlink your login from {roommate.name}?</span>
            <button onClick={unlink} disabled={unlinking} className="btn-danger">
              Unlink
            </button>
            <button onClick={() => setConfirmUnlink(false)} className="btn-secondary">
              Cancel
            </button>
          </div>
        ) : (
          <button onClick={() => setConfirmUnlink(true)} className="btn-secondary text-xs">
            Not {roommate.name}?
          </button>
        )}
      </div>

      {error && <ErrorAlert message={error} onRetry={load} />}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <BalanceCard name="Balance to date" balance={dash.balance} />
        <SummaryCard
          label={latest ? `Bill · ${formatMonth(latest.month)}` : 'Latest bill'}
          value={formatMoney(latest?.total_bill)}
          subtext={latest ? `${formatNumber(latest.total_units)} units @ ${formatMoney(latest.rate_per_unit)}` : 'No bill yet'}
        />
        <SummaryCard
          label="Average usage"
          value={avgUnits === null ? '—' : `${formatNumber(avgUnits, 0)} units`}
          subtext={`Per month, over ${billed.length} month${billed.length === 1 ? '' : 's'}`}
        />
        <SummaryCard
          label="Paid so far"
          value={formatMoney(dash.total_recharges_cumulative)}
          subtext={`Billed so far: ${formatMoney(dash.total_bill_cumulative)}`}
        />
      </div>

      <div className="card">
        <h3 className="mb-1 text-lg font-semibold text-slate-900">By meter</h3>
        <p className="mb-4 text-sm text-slate-500">
          Main meter: your energy charge vs your main payments. DG: your share of the DG bill vs
          your DG payments.
        </p>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Meter</th>
                <th className="text-right">Billed so far</th>
                <th className="text-right">Paid so far</th>
                <th className="text-right">Balance</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {[
                ['main', dash.main_bill_cumulative, dash.main_recharges_cumulative, dash.main_balance],
                ['dg', dash.dg_bill_cumulative, dash.dg_recharges_cumulative, dash.dg_balance],
              ].map(([meter, billedSoFar, paidSoFar, balance]) => (
                <tr key={meter}>
                  <td>
                    <MeterBadge meter={meter} />
                  </td>
                  <td className="text-right tabular-nums">{formatMoney(billedSoFar)}</td>
                  <td className="text-right tabular-nums">{formatMoney(paidSoFar)}</td>
                  <td
                    className={`text-right font-medium tabular-nums ${
                      balance > 0 ? 'text-rose-600' : balance < 0 ? 'text-emerald-600' : ''
                    }`}
                  >
                    {formatMoney(balance)}
                    <span className="ml-1 text-xs font-normal text-slate-500">
                      {balance > 0 ? 'owed' : balance < 0 ? 'credit' : ''}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="card scroll-mt-4" ref={readingCard}>
          <h3 className="mb-4 text-lg font-semibold text-slate-900">Submit meter reading</h3>
          <ReadingForm
            months={months}
            month={formMonth}
            onMonthChange={setReadingMonth}
            roommateId={roommate.id}
            onSaved={load}
          />
        </div>
        <div className="card">
          <h3 className="mb-4 text-lg font-semibold text-slate-900">Add a payment</h3>
          <PaymentForm roommateId={roommate.id} onSaved={load} />
        </div>
      </div>

      <div className="card">
        <h3 className="mb-4 text-lg font-semibold text-slate-900">Units per month</h3>
        <UsageChart months={months} />
      </div>

      <div className="card">
        <h3 className="mb-4 text-lg font-semibold text-slate-900">Monthly history</h3>
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Month</th>
                <th className="text-right">Reading</th>
                <th className="text-right">Own units</th>
                <th className="text-right">Common units</th>
                <th className="text-right">Bill</th>
                <th className="text-right">Paid</th>
                <th className="text-right">Balance</th>
                <th className="text-center">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {history.map((m) => (
                <tr key={m.month}>
                  <td className="font-medium">{formatMonth(m.month)}</td>
                  <td className="text-right tabular-nums">
                    {m.current_reading === null ? (
                      <span className={m.is_active ? 'text-amber-600' : 'text-slate-400'}>
                        {m.is_active ? 'Due' : '—'}
                      </span>
                    ) : (
                      formatNumber(m.current_reading)
                    )}
                  </td>
                  <td className="text-right tabular-nums">{formatNumber(m.sub_units)}</td>
                  <td className="text-right tabular-nums">{formatNumber(m.common_share)}</td>
                  <td className="text-right tabular-nums">
                    {m.billed ? formatMoney(m.total_bill) : <span className="text-slate-400">Pending</span>}
                  </td>
                  <td className="text-right tabular-nums">
                    {formatMoney(m.recharges)}
                    {m.recharges_dg > 0 && (
                      <span className="block text-xs text-slate-500">
                        Main {formatMoney(m.recharges_main)} · DG {formatMoney(m.recharges_dg)}
                      </span>
                    )}
                  </td>
                  <td
                    className={`text-right font-medium tabular-nums ${
                      m.balance > 0 ? 'text-rose-600' : m.balance < 0 ? 'text-emerald-600' : ''
                    }`}
                  >
                    {formatMoney(m.balance)}
                  </td>
                  <td className="whitespace-nowrap text-center">
                    {confirmDeleteReading === m.month ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="text-xs text-slate-600">Delete reading?</span>
                        <button onClick={() => removeReading(m.month)} className="btn-danger text-xs">
                          Delete
                        </button>
                        <button
                          onClick={() => setConfirmDeleteReading(null)}
                          className="btn-secondary text-xs"
                        >
                          Keep
                        </button>
                      </span>
                    ) : m.current_reading !== null ? (
                      <span className="inline-flex gap-2">
                        <button onClick={() => editReading(m.month)} className="btn-secondary text-xs">
                          Edit
                        </button>
                        <button
                          onClick={() => setConfirmDeleteReading(m.month)}
                          className="btn-danger text-xs"
                        >
                          Delete
                        </button>
                      </span>
                    ) : m.is_active ? (
                      <button onClick={() => editReading(m.month)} className="btn-secondary text-xs">
                        Add
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
              {history.length === 0 && (
                <tr>
                  <td colSpan={8} className="py-6 text-center text-slate-500">
                    No months yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h3 className="mb-4 text-lg font-semibold text-slate-900">My payments</h3>
        {payments.length === 0 ? (
          <p className="text-sm text-slate-500">No payments yet.</p>
        ) : (
          <ul className="divide-y divide-slate-200">
            {payments.map((p) => (
              <li key={p.id} className="flex items-center justify-between gap-3 py-2">
                <div>
                  <p className="flex items-center gap-2 font-medium tabular-nums text-slate-800">
                    {formatMoney(p.amount)}
                    <MeterBadge meter={p.meter} />
                  </p>
                  <p className="text-xs text-slate-500">
                    {p.date}
                    {p.notes ? ` · ${p.notes}` : ''}
                  </p>
                </div>
                {confirmDelete === p.id ? (
                  <div className="flex gap-2">
                    <button onClick={() => removePayment(p.id)} className="btn-danger text-xs">
                      Delete
                    </button>
                    <button onClick={() => setConfirmDelete(null)} className="btn-secondary text-xs">
                      Keep
                    </button>
                  </div>
                ) : (
                  <button onClick={() => setConfirmDelete(p.id)} className="btn-secondary text-xs">
                    Remove
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export { LinkRoommateCard };
export default MyDashboard;
