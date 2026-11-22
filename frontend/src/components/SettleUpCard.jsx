import { useEffect, useState } from 'react';
import { createSettlement, getSettleUp, respondSettlement } from '../api';
import { formatMoney, formatMonth, today } from '../format';
import ErrorAlert from './ErrorAlert';

// Who pays whom so that everyone ends up even (see calc.settle_up). "I paid"
// puts an amount in verification; it only counts once the receiver marks it
// received. The backend says which buttons each person gets (s.actions).
//
// refreshKey: changes whenever the balances do (the card reloads then).
// myId: the viewer's roommate, if linked. isOwner: may send for anyone.
// personal: only what involves the viewer (My dashboard).

const RECENT = 3; // finished payments shown without expanding

const STATUS = {
  verifying: ['In verification', 'bg-amber-100 text-amber-800'],
  received: ['Received', 'bg-emerald-100 text-emerald-800'],
  not_received: ['Not received', 'bg-rose-100 text-rose-700'],
  cancelled: ['Cancelled', 'bg-slate-100 text-slate-600'],
  undone: ['Undone', 'bg-slate-100 text-slate-600'],
  undo: ['Undo requested', 'bg-amber-100 text-amber-800'],
};

function StatusBadge({ status }) {
  const [label, tone] = STATUS[status];
  return (
    <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${tone}`}>
      {label}
    </span>
  );
}

function paymentTitle(s, myId) {
  const amount = formatMoney(s.amount);
  const received = s.status === 'received';
  if (s.from_roommate_id === myId) return `You paid ${s.to_roommate} ${amount}`;
  if (s.to_roommate_id === myId) {
    return received ? `${s.from_roommate} paid you ${amount}` : `${s.from_roommate} says they paid you ${amount}`;
  }
  return `${s.from_roommate} → ${s.to_roommate} ${amount}`;
}

function paymentDetail(s, myId) {
  const payer = s.from_roommate_id === myId;
  const receiver = s.to_roommate_id === myId;
  if (s.status === 'verifying') {
    if (!s.receiver_joined) {
      return `${s.to_roommate} hasn't joined yet. It waits until they join with the owner's invite.${
        payer ? " Don't pay again." : ''
      }`;
    }
    if (receiver) return 'Check your bank or UPI app first.';
    return `Waiting for ${s.to_roommate} to confirm.${payer ? " Don't pay again." : ''}${
      s.emailed ? ' They were emailed.' : ''
    }`;
  }
  if (s.undo_side) {
    const [asker, other] =
      s.undo_side === 'payer' ? [s.from_roommate, s.to_roommate] : [s.to_roommate, s.from_roommate];
    return `${asker} asked to undo this. It stays received unless ${other} agrees.`;
  }
  if (s.status === 'not_received') return `${s.to_roommate}: “${s.reject_reason}”`;
  if (s.status === 'received' && s.responded_by_email) return `Confirmed by ${s.responded_by_email}`;
  return null;
}

// A payment already recorded, with what this person can do about it.
function Payment({ settlement: s, myId, saving, onAction }) {
  const [asking, setAsking] = useState(null); // the action being confirmed
  const [reason, setReason] = useState('');
  const can = (action) => s.actions.includes(action);
  const detail = paymentDetail(s, myId);

  const act = async (action) => {
    if (await onAction(s.id, action, action === 'not_received' ? reason.trim() : undefined)) setAsking(null);
  };
  const button = (action, label, tone = 'btn-secondary', confirmFirst = true) =>
    can(action) && (
      <button
        onClick={() => (confirmFirst ? setAsking(action) : act(action))}
        disabled={saving}
        className={`${tone} text-xs`}
      >
        {label}
      </button>
    );
  const confirmations = {
    received: [`Did ${formatMoney(s.amount)} reach you?`, 'Yes, received'],
    cancel: ['Cancel this payment?', 'Yes, cancel it'],
    request_undo: ['Ask to undo? Both of you have to agree.', 'Ask to undo'],
  };

  return (
    <li className="py-3" data-testid="settlement">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-semibold text-slate-900">{paymentTitle(s, myId)}</span>
        <StatusBadge status={s.undo_side ? 'undo' : s.status} />
      </div>
      <p className="mt-1 break-words text-xs text-slate-500">
        {s.date}
        {detail && ` · ${detail}`}
      </p>

      {asking === 'not_received' && can(asking) ? (
        <form
          className="mt-2 flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            act('not_received');
          }}
        >
          <input
            aria-label="Reason it wasn't received"
            placeholder="Why? e.g. nothing in my bank"
            maxLength={200}
            autoFocus
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="min-w-0 flex-1"
          />
          <button type="submit" disabled={saving || !reason.trim()} className="btn-danger text-xs">
            Send
          </button>
          <button type="button" onClick={() => setAsking(null)} className="btn-secondary text-xs">
            Back
          </button>
        </form>
      ) : asking && can(asking) ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-600">{confirmations[asking][0]}</span>
          <button onClick={() => act(asking)} disabled={saving} className="btn-primary text-xs">
            {confirmations[asking][1]}
          </button>
          <button onClick={() => setAsking(null)} className="btn-secondary text-xs">
            Back
          </button>
        </div>
      ) : (
        s.actions.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {button('received', 'Mark received', 'btn-primary')}
            {button('not_received', 'Not received', 'btn-danger')}
            {button('cancel', 'Cancel')}
            {button('request_undo', 'Undo')}
            {button('agree_undo', 'Agree to undo', 'btn-danger', false)}
            {button('decline_undo', 'Keep it received', 'btn-secondary', false)}
            {button('withdraw_undo', 'Withdraw request', 'btn-secondary', false)}
          </div>
        )
      )}
    </li>
  );
}

// A suggested payment, and the form to enter how much of it was paid.
function Transfer({ transfer: t, myId, isOwner, hasWaiting, saving, onSend }) {
  const [amount, setAmount] = useState(null); // null: form closed
  const payer = t.from_roommate_id === myId;
  const receiver = t.to_roommate_id === myId;
  // With one already waiting, the receiver confirms that instead of recording another.
  const canEnter = payer || (receiver && !hasWaiting) || (isOwner && !receiver);
  const label = payer ? 'I paid' : receiver ? `${t.from_roommate} paid me` : `${t.from_roommate} paid`;

  const submit = async (e) => {
    e.preventDefault();
    if (await onSend(t, parseFloat(amount))) setAmount(null);
  };

  return (
    <li className="py-3" data-testid="transfer">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm text-slate-700">
          <span className="font-semibold text-slate-900">{payer ? 'You' : t.from_roommate}</span>
          {payer ? ' pay ' : ' pays '}
          <span className="font-semibold text-slate-900">{receiver ? 'you' : t.to_roommate}</span>
        </span>
        <span className="flex items-center gap-3">
          <span className="font-semibold tabular-nums text-slate-900">{formatMoney(t.amount)}</span>
          {canEnter && amount === null && (
            <button onClick={() => setAmount(String(t.amount))} className="btn-primary text-xs">
              {label}
            </button>
          )}
        </span>
      </div>
      {canEnter && amount !== null && (
        <form onSubmit={submit} className="mt-2 flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-2 text-xs text-slate-600">
            Amount (₹)
            <input
              aria-label="Amount paid"
              type="number"
              inputMode="decimal"
              step="0.01"
              min="0.01"
              autoFocus
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="w-32 text-right"
            />
          </label>
          <button type="submit" disabled={saving || !(parseFloat(amount) > 0)} className="btn-primary text-xs">
            {receiver ? 'Record as received' : 'Send for verification'}
          </button>
          <button type="button" onClick={() => setAmount(null)} className="btn-secondary text-xs">
            Back
          </button>
          <p className="w-full text-xs text-slate-500">
            {receiver
              ? 'You got the money, so it’s settled straight away.'
              : `It counts once ${t.to_roommate} marks it received. Enter less if it was a part payment.`}
          </p>
        </form>
      )}
    </li>
  );
}

function PlanNotes({ plan }) {
  return (
    <>
      <p className="mb-4 mt-1 text-sm text-slate-500">
        Pay each other back so that everyone ends up even
        {plan.through_month ? `, for the bills up to ${formatMonth(plan.through_month)}` : ''}.
        {plan.meter_balance > 0 && (
          <>
            {' '}
            The {formatMoney(plan.meter_balance)} still in the meter is prepaid electricity, so it stays as credit
            for whoever paid it in.
          </>
        )}
        {plan.later_payments_total > 0 && (
          <>
            {' '}
            {formatMoney(plan.later_payments_total)} paid since then is for a month not settled yet; it&apos;s
            settled once that month is complete.
          </>
        )}
      </p>

      {plan.waiting_for.length > 0 && (
        <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {plan.through_month ? 'Later months aren’t included yet:' : 'Settle up can’t open yet:'}
          <ul className="mt-1 list-disc pl-5">
            {plan.waiting_for.map((w) => (
              <li key={w.month}>
                {formatMonth(w.month)} needs{' '}
                {[w.missing.length > 0 && `readings from ${w.missing.join(', ')}`, w.needs_bill && 'its bill']
                  .filter(Boolean)
                  .join(' and ')}
              </li>
            ))}
          </ul>
        </div>
      )}

      {plan.future_payments.length > 0 && (
        <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          These payments are dated after today, so the date is probably wrong. Check them under Recharges /
          Payments:
          <ul className="mt-1 list-disc pl-5">
            {plan.future_payments.map((p) => (
              <li key={p.id}>
                {p.roommate} {formatMoney(p.amount)}
                {p.meter === 'dg' ? ' (DG)' : ''} on {p.date}
              </li>
            ))}
          </ul>
        </div>
      )}

      {Math.abs(plan.unpaid_total) >= 0.01 && (
        <p className="mb-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-600">
          {plan.unpaid_total > 0 ? (
            <>
              <span className="font-medium">{formatMoney(plan.unpaid_total)}</span> of electricity has no
              recorded payment (recharges not entered in the app, or a mistake in the month&apos;s meter
              figures). It&apos;s shared equally, <span className="font-medium">{formatMoney(plan.unpaid_each)}</span>{' '}
              each, and included below.
            </>
          ) : (
            <>
              Recorded payments are <span className="font-medium">{formatMoney(-plan.unpaid_total)}</span> more
              than the bills plus what&apos;s in the meter (a payment entered twice, or in the wrong month?).
              It&apos;s shared equally, <span className="font-medium">{formatMoney(-plan.unpaid_each)}</span> each,
              and included below.
            </>
          )}
        </p>
      )}
    </>
  );
}

// What's owed until it's received, with how much of that is waiting.
function Owed({ plan, myId, personal }) {
  const debtors = plan.positions.filter(
    (p) => p.balance >= 0.02 && (personal ? p.roommate_id === myId : p.waiting_out > 0)
  );
  return debtors.map((p) => (
    <p key={p.roommate_id} className="mb-2 text-sm font-medium text-slate-900" data-testid="owed">
      {p.roommate_id === myId ? 'You owe' : `${p.name} owes`} {formatMoney(p.balance)}
      {p.waiting_out > 0 && (
        <span className="font-normal text-amber-700"> ({formatMoney(p.waiting_out)} waiting)</span>
      )}
    </p>
  ));
}

function SettleUpCard({ refreshKey, myId, isOwner = false, personal = false, onChanged }) {
  const [plan, setPlan] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = () =>
    getSettleUp()
      .then(setPlan)
      .catch((err) => setError(err.message));

  useEffect(() => {
    load();
    // The other person may have answered while the app was in the background.
    window.addEventListener('focus', load);
    return () => window.removeEventListener('focus', load);
  }, [refreshKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const change = async (request) => {
    setSaving(true);
    setError(null);
    try {
      await request();
      await onChanged();
      return true;
    } catch (err) {
      setError(err.message);
      await load(); // it may have changed on the other person's phone
      return false;
    } finally {
      setSaving(false);
    }
  };

  const send = (t, amount) =>
    change(() =>
      createSettlement({
        from_roommate_id: t.from_roommate_id,
        to_roommate_id: t.to_roommate_id,
        amount,
        date: today(),
      })
    );
  const respond = (id, action, reason) => change(() => respondSettlement(id, action, reason));

  const retry = () => {
    setError(null);
    load();
  };

  if (!plan) return error ? <ErrorAlert message={error} onRetry={retry} /> : null;
  // The web app deploys faster than the backend: an older one has no verification.
  if (!plan.positions || !plan.waiting_for) {
    return (
      <div className="card text-sm text-slate-500">Settle up is being updated. Check back in a few minutes.</div>
    );
  }

  const involvesMe = (row) => !personal || row.from_roommate_id === myId || row.to_roommate_id === myId;
  const payments = plan.settlements.filter(involvesMe);
  const isOpen = (s) => s.status === 'verifying' || Boolean(s.undo_side);
  const open = payments.filter(isOpen);
  const closed = payments.filter((s) => !isOpen(s)).reverse();
  const transfers = plan.transfers.filter(involvesMe);
  const hasWaiting = (t) =>
    open.some(
      (s) =>
        s.status === 'verifying' &&
        s.from_roommate_id === t.from_roommate_id &&
        s.to_roommate_id === t.to_roommate_id
    );

  return (
    <div className="card" data-testid={personal ? 'my-settle-up' : 'settle-up'}>
      <h2 className="text-lg font-semibold text-slate-900">Settle up</h2>
      <PlanNotes plan={plan} />
      {error && (
        <div className="mb-3">
          <ErrorAlert message={error} />
        </div>
      )}
      <Owed plan={plan} myId={myId} personal={personal} />

      {open.length > 0 && (
        <ul className="mb-3 divide-y divide-amber-200 rounded-md border border-amber-200 bg-amber-50/50 px-3">
          {open.map((s) => (
            <Payment key={s.id} settlement={s} myId={myId} saving={saving} onAction={respond} />
          ))}
        </ul>
      )}

      {transfers.length > 0 ? (
        <ul className="divide-y divide-slate-200">
          {transfers.map((t) => (
            <Transfer
              key={`${t.from_roommate_id}-${t.to_roommate_id}`}
              transfer={t}
              myId={myId}
              isOwner={isOwner && !personal}
              hasWaiting={hasWaiting(t)}
              saving={saving}
              onSend={send}
            />
          ))}
        </ul>
      ) : (
        plan.through_month &&
        open.length === 0 &&
        plan.waiting_for.length === 0 && (
          <p className="text-sm font-medium text-emerald-700">
            {personal ? 'You’re settled up.' : 'Everyone is settled up.'}
          </p>
        )
      )}

      {closed.length > 0 && (
        <div className="mt-5">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Payment history</h3>
          {/* The latest always show, so one just answered doesn't seem to vanish. */}
          <ul className="divide-y divide-slate-100">
            {closed.slice(0, RECENT).map((s) => (
              <Payment key={s.id} settlement={s} myId={myId} saving={saving} onAction={respond} />
            ))}
          </ul>
          {closed.length > RECENT && (
            <details>
              <summary className="cursor-pointer py-2 text-xs text-slate-500">
                {closed.length - RECENT} older
              </summary>
              <ul className="divide-y divide-slate-100">
                {closed.slice(RECENT).map((s) => (
                  <Payment key={s.id} settlement={s} myId={myId} saving={saving} onAction={respond} />
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

export default SettleUpCard;
