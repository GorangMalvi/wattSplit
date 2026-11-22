import { useState } from 'react';
import MeterReplacement from './MeterReplacement';

const fmt = (v) => (v === null || v === undefined ? '-' : v.toLocaleString(undefined, { maximumFractionDigits: 2 }));

// rows: { roommate_id, name, previous_reading, previous_editable, start_reading,
//         fallback_reading, current_reading, sub_units }. previous_editable: no
// reading last month, so the start reading can be typed in (saved as
// start_reading); left blank, units count from fallback_reading (last known).
// old_meter_final: set when the meter was replaced that month (MeterReplacement).
// onUpdate(roommateId, { current_reading } | { start_reading }); null clears.
// canEdit(roommateId): whether this user may change that roommate's readings.
// mainUnits: the main meter's units this month, for the total row (optional).
function ReadingsTable({ rows, onUpdate, loading, canEdit = () => true, mainUnits = null }) {
  const counted = rows.filter((r) => r.sub_units !== null && r.sub_units !== undefined);
  const totalUnits = counted.reduce((sum, r) => sum + r.sub_units, 0);
  const [drafts, setDrafts] = useState({});
  const key = (roommateId, field) => `${roommateId}:${field}`;

  const handleChange = (roommateId, field, value) => {
    setDrafts((prev) => ({ ...prev, [key(roommateId, field)]: value }));
  };

  const draftOf = (row, field) => drafts[key(row.roommate_id, field)];
  const clearDrafts = (row, ...fields) =>
    setDrafts((prev) => {
      const next = { ...prev };
      for (const field of fields) delete next[key(row.roommate_id, field)];
      return next;
    });

  // A first reading has nothing to count from until a start reading is given.
  const needsStart = (row) => row.previous_editable && row.start_reading === null && row.fallback_reading === null;
  const endHeld = (row) => {
    const typed = parseFloat(draftOf(row, 'current_reading'));
    return needsStart(row) && typed >= 0 && typed !== row.current_reading;
  };
  // A start of 0 is only right for a brand-new meter, so it's asked about.
  const zeroTyped = (row) => row.start_reading !== 0 && parseFloat(draftOf(row, 'start_reading')) === 0;

  const saveStart = (row, start, extra = {}) => {
    const fields = { start_reading: start, ...extra };
    if (endHeld(row)) fields.current_reading = parseFloat(draftOf(row, 'current_reading'));
    clearDrafts(row, 'start_reading', 'current_reading');
    onUpdate(row.roommate_id, fields);
  };

  const handleBlur = (row, field) => {
    const value = draftOf(row, field);
    if (value === undefined) return;
    if (value.trim() === '') {
      clearDrafts(row, field);
      if (row[field] !== null && row[field] !== undefined) onUpdate(row.roommate_id, { [field]: null });
      return;
    }
    const numeric = parseFloat(value);
    if (Number.isNaN(numeric) || numeric < 0 || numeric === row[field]) {
      clearDrafts(row, field);
      return;
    }
    if (field === 'start_reading') {
      if (numeric !== 0) saveStart(row, numeric);
      return;
    }
    if (needsStart(row)) return; // held until the start reading is in
    clearDrafts(row, field);
    onUpdate(row.roommate_id, { [field]: numeric });
  };

  const input = (row, field, placeholder) => {
    const k = key(row.roommate_id, field);
    return (
      <input
        type="number"
        step="0.01"
        min="0"
        aria-label={`${row.name} ${field === 'start_reading' ? 'start' : 'current'} reading`}
        placeholder={placeholder}
        value={drafts[k] !== undefined ? drafts[k] : row[field] ?? ''}
        disabled={loading}
        onChange={(e) => handleChange(row.roommate_id, field, e.target.value)}
        onBlur={() => handleBlur(row, field)}
        className="w-32 text-right"
      />
    );
  };

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Roommate</th>
            <th className="text-right">Previous Reading</th>
            <th className="text-right">Current Reading</th>
            <th className="text-right">Units Used</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200">
          {rows.map((row) => {
            const editable = canEdit(row.roommate_id);
            return (
              <tr key={row.roommate_id}>
                <td className="font-medium">{row.name}</td>
                <td className="text-right tabular-nums">
                  {row.previous_editable && editable ? (
                    <div className="flex flex-col items-end gap-1">
                      {input(row, 'start_reading', 'Start')}
                      {zeroTyped(row) ? (
                        <span className="flex flex-wrap items-center justify-end gap-1 text-xs text-amber-700">
                          Is this a brand-new meter?
                          <button
                            onClick={() => saveStart(row, 0, { new_meter: true })}
                            disabled={loading}
                            className="btn-secondary px-2 py-1 text-xs"
                          >
                            Yes, it starts at 0
                          </button>
                          <button
                            onClick={() => clearDrafts(row, 'start_reading')}
                            className="btn-secondary px-2 py-1 text-xs"
                          >
                            No
                          </button>
                        </span>
                      ) : endHeld(row) ? (
                        <span className="text-xs text-amber-700">
                          Not saved yet: enter what the meter showed at the start, or on moving in
                        </span>
                      ) : (
                        <span className="text-xs text-slate-400">
                          No reading last month
                          {row.start_reading === null &&
                            row.fallback_reading !== null &&
                            `, counting from ${fmt(row.fallback_reading)}`}
                        </span>
                      )}
                    </div>
                  ) : (
                    <span
                      title={
                        !row.previous_editable
                          ? "Last month's reading"
                          : row.start_reading === null
                            ? 'Last known reading'
                            : 'Start reading'
                      }
                    >
                      {fmt(row.previous_reading)}
                    </span>
                  )}
                </td>
                <td className="text-right">
                  {editable ? (
                    <div className="flex flex-col items-end gap-1">
                      {input(row, 'current_reading')}
                      <MeterReplacement
                        name={row.name}
                        previous={row.previous_reading}
                        current={row.current_reading}
                        start={row.start_reading}
                        oldFinal={row.old_meter_final}
                        disabled={loading}
                        onSave={(fields) => onUpdate(row.roommate_id, fields)}
                      />
                    </div>
                  ) : (
                    <span className="tabular-nums">
                      {fmt(row.current_reading)}
                      {row.old_meter_final !== null && (
                        <span className="block text-xs text-slate-400">Meter replaced</span>
                      )}
                    </span>
                  )}
                </td>
                <td className="text-right tabular-nums">{fmt(row.sub_units)}</td>
              </tr>
            );
          })}
          {rows.length === 0 && (
            <tr>
              <td colSpan={4} className="py-6 text-center text-slate-500">
                No active roommates for this month.
              </td>
            </tr>
          )}
        </tbody>
        {rows.length > 0 && (
          <tfoot className="border-t-2 border-slate-200 bg-slate-50">
            <tr>
              <td className="font-semibold text-slate-900">Total</td>
              <td colSpan={2} className="text-right text-xs text-slate-500">
                {counted.length < rows.length &&
                  `${counted.length} of ${rows.length} roommates have readings`}
                {mainUnits !== null && counted.length > 0 && (
                  <span className="ml-3">
                    Main meter {fmt(mainUnits)} · Common {fmt(mainUnits - totalUnits)}
                  </span>
                )}
              </td>
              <td className="text-right font-semibold tabular-nums text-slate-900">
                {counted.length ? fmt(totalUnits) : '-'}
              </td>
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}

export default ReadingsTable;
