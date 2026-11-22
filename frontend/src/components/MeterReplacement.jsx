import { useState } from 'react';
import { formatNumber } from '../format';

const num = (text) => {
  const n = parseFloat(text);
  return Number.isNaN(n) || n < 0 ? null : n;
};

// "Meter replaced?": the old meter's last reading, the new one's start and its
// month-end reading, saved together. The month is then billed
// (old last − previous) + (end − new start).
//
// previous: what the old meter counts from. current, start, oldFinal: as saved.
// typedEnd: a month-end reading typed but not saved yet.
// onSave(fields) resolves to true once saved.
function MeterReplacement({ name, previous, current, start, oldFinal, typedEnd, onSave, disabled = false }) {
  const [draft, setDraft] = useState(null); // null: closed
  const replaced = oldFinal !== null && oldFinal !== undefined;

  if (!replaced && (previous === null || previous === undefined)) return null; // a first reading: just a start reading

  if (!draft) {
    const open = () =>
      setDraft({
        oldLast: replaced ? String(oldFinal) : '',
        newStart: replaced ? String(start) : '',
        end: String(typedEnd ?? current ?? ''),
        isNew: replaced && start === 0,
      });
    return (
      <div className="text-xs text-slate-500">
        {replaced && `Meter replaced: old ended ${formatNumber(oldFinal)}, new started ${formatNumber(start)} · `}
        <button
          type="button"
          onClick={open}
          disabled={disabled}
          aria-label={replaced ? `Edit ${name} meter replacement` : `${name} meter replaced`}
          className="px-0 py-1 text-xs text-indigo-600 underline"
        >
          {replaced ? 'Edit' : 'Meter replaced?'}
        </button>
      </div>
    );
  }

  const [oldLast, newStart, end] = [draft.oldLast, draft.newStart, draft.end].map(num);
  const filled = oldLast !== null && newStart !== null && end !== null;
  const problem = !filled
    ? null
    : oldLast < previous
      ? `The old meter can't end below ${formatNumber(previous)}.`
      : end < newStart
        ? "The new meter can't end below where it started."
        : null;
  const ready = filled && !problem && (newStart !== 0 || draft.isNew);

  const save = async (fields) => {
    if (await onSave(fields)) setDraft(null);
  };
  const field = (key, label) => (
    <label className="flex items-center justify-between gap-2 text-xs text-slate-600">
      {label}
      <input
        type="number"
        inputMode="decimal"
        step="0.01"
        min="0"
        aria-label={`${name} ${label.toLowerCase()}`}
        value={draft[key]}
        onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
        className="w-28 text-right"
      />
    </label>
  );

  return (
    <div className="w-full max-w-xs space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3 text-left">
      <p className="text-xs font-semibold text-slate-700">Meter replaced this month</p>
      {field('oldLast', 'Old meter, last reading')}
      {field('newStart', 'New meter, start')}
      {field('end', 'New meter, month end')}
      {newStart === 0 && (
        <label className="flex items-center gap-2 text-xs text-amber-700">
          <input type="checkbox" checked={draft.isNew} onChange={(e) => setDraft({ ...draft, isNew: e.target.checked })} />
          The new meter really starts at 0
        </label>
      )}
      {problem ? (
        <p className="text-xs text-rose-600">{problem}</p>
      ) : (
        filled && (
          <p className="text-xs text-slate-600">
            {formatNumber(oldLast - previous)} on the old meter + {formatNumber(end - newStart)} on the new one ={' '}
            <span className="font-semibold">{formatNumber(oldLast - previous + end - newStart)} units</span>
          </p>
        )
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={disabled || !ready}
          onClick={() =>
            save({
              old_meter_final: oldLast,
              start_reading: newStart,
              current_reading: end,
              ...(newStart === 0 && { new_meter: true }),
            })
          }
          className="btn-primary text-xs"
        >
          Save replacement
        </button>
        {replaced && (
          <button
            type="button"
            disabled={disabled}
            // The new meter's reading means nothing on the old one, so it's cleared when it's lower.
            onClick={() => save({ old_meter_final: null, ...(current < previous && { current_reading: null }) })}
            className="btn-danger text-xs"
          >
            It wasn&apos;t replaced
          </button>
        )}
        <button type="button" onClick={() => setDraft(null)} className="btn-secondary text-xs">
          Back
        </button>
      </div>
    </div>
  );
}

export default MeterReplacement;
