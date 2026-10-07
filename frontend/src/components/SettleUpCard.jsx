import { useEffect, useState } from 'react';
import { createSettlement, deleteSettlement, getSettleUp } from '../api';
import { formatMoney, today } from '../format';
import ErrorAlert from './ErrorAlert';

// Who pays whom so that every balance reaches zero. Electricity nobody has
// recorded paying for is shared equally (see calc.settle_up). "Mark as paid"
// records the payment, which moves both roommates' balances.
//
// refreshKey: changes whenever the balances do (the card reloads then).
// canRecord(fromId, toId): whether this user may record that payment.
function SettleUpCard({ refreshKey, canRecord, onChanged }) {
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState(null);
  const [confirming, setConfirming] = useState(null); // transfer key
  const [saving, setSaving] = useState(false);

  const load = () =>
    getSettleUp()
      .then((d) => {
        setPlan(d);
        setError(null);
      })
      .catch((err) => setError(err.message));

  useEffect(() => {
    load();
  }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const record = async (t) => {
    setSaving(true);
    setError(null);
    try {
      await createSettlement({
        from_roommate_id: t.from_roommate_id,
        to_roommate_id: t.to_roommate_id,
        amount: t.amount,
        date: today(),
        notes: 'Settle up',
      });
      setConfirming(null);
      await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const undo = async (id) => {
    setError(null);
    try {
      await deleteSettlement(id);
      await onChanged();
    } catch (err) {
      setError(err.message);
    }
  };

  if (!plan) return error ? <ErrorAlert message={error} onRetry={load} /> : null;

  const recent = [...plan.settlements].reverse().slice(0, 5);
  const keyOf = (t) => `${t.from_roommate_id}-${t.to_roommate_id}`;

  return (
    <div className="card">
      <h2 className="text-lg font-semibold text-slate-900">Settle up</h2>
      <p className="mb-4 mt-1 text-sm text-slate-500">
        Pay each other back so that everyone ends up even.
      </p>
      {error && <ErrorAlert message={error} />}

      {Math.abs(plan.unpaid_total) >= 0.01 && (
        <p className="mb-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
          {plan.unpaid_total > 0 ? (
            <>
              <span className="font-medium">{formatMoney(plan.unpaid_total)}</span> of electricity has no
              recorded payment (the meter&apos;s starting balance, or recharges not entered in the app). It&apos;s
              shared equally, <span className="font-medium">{formatMoney(plan.unpaid_each)}</span> each, and
              included below.
            </>
          ) : (
            <>
              Recorded payments are <span className="font-medium">{formatMoney(-plan.unpaid_total)}</span> more
              than the bills so far (credit left in the meter). It&apos;s shared equally,{' '}
              <span className="font-medium">{formatMoney(-plan.unpaid_each)}</span> each, and included below.
            </>
          )}
        </p>
      )}

      {plan.transfers.length === 0 ? (
        <p className="text-sm font-medium text-emerald-700">Everyone is settled up.</p>
      ) : (
        <ul className="divide-y divide-slate-200">
          {plan.transfers.map((t) => (
            <li key={keyOf(t)} className="flex flex-wrap items-center justify-between gap-3 py-3">
              <span className="text-sm text-slate-700">
                <span className="font-semibold text-slate-900">{t.from_roommate}</span> pays{' '}
                <span className="font-semibold text-slate-900">{t.to_roommate}</span>
              </span>
              <span className="flex items-center gap-3">
                <span className="font-semibold tabular-nums text-slate-900">{formatMoney(t.amount)}</span>
                {canRecord(t.from_roommate_id, t.to_roommate_id) &&
                  (confirming === keyOf(t) ? (
                    <span className="flex items-center gap-2">
                      <span className="text-xs text-slate-500">Paid today?</span>
                      <button onClick={() => record(t)} disabled={saving} className="btn-primary text-xs">
                        Yes, record it
                      </button>
                      <button onClick={() => setConfirming(null)} className="btn-secondary text-xs">
                        Cancel
                      </button>
                    </span>
                  ) : (
                    <button onClick={() => setConfirming(keyOf(t))} className="btn-secondary text-xs">
                      Mark as paid
                    </button>
                  ))}
              </span>
            </li>
          ))}
        </ul>
      )}

      {recent.length > 0 && (
        <div className="mt-5">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Recorded payments</h3>
          <ul className="divide-y divide-slate-100 text-sm">
            {recent.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3 py-2">
                <span className="text-slate-600">
                  {s.date} · {s.from_roommate} paid {s.to_roommate}
                </span>
                <span className="flex items-center gap-3">
                  <span className="tabular-nums text-slate-800">{formatMoney(s.amount)}</span>
                  {canRecord(s.from_roommate_id, s.to_roommate_id) && (
                    <button onClick={() => undo(s.id)} className="btn-secondary px-2 py-1 text-xs">
                      Undo
                    </button>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default SettleUpCard;
