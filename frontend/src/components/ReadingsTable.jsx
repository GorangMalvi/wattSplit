import { useState } from 'react';

const fmt = (v) => (v === null || v === undefined ? '-' : v.toLocaleString(undefined, { maximumFractionDigits: 2 }));

// rows: { roommate_id, name, previous_reading, previous_editable, start_reading,
//         current_reading, sub_units }. previous_editable: no reading last month,
// so the start reading can be typed in (saved as start_reading).
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

  const handleBlur = (row, field) => {
    const k = key(row.roommate_id, field);
    const value = drafts[k];
    if (value === undefined) return;
    setDrafts((prev) => {
      const next = { ...prev };
      delete next[k];
      return next;
    });
    if (value.trim() === '') {
      if (row[field] !== null && row[field] !== undefined) onUpdate(row.roommate_id, { [field]: null });
      return;
    }
    const numeric = parseFloat(value);
    if (Number.isNaN(numeric) || numeric < 0 || numeric === row[field]) return;
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
                      <span className="text-xs text-slate-400">No reading last month</span>
                    </div>
                  ) : (
                    <span title={row.previous_editable ? 'Start reading' : "Last month's reading"}>
                      {fmt(row.previous_reading)}
                    </span>
                  )}
                </td>
                <td className="text-right">
                  {editable ? input(row, 'current_reading') : <span className="tabular-nums">{fmt(row.current_reading)}</span>}
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
