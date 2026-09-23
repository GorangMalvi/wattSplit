import { useState } from 'react';

function ReadingsTable({ rows, onUpdate, loading }) {
  const [drafts, setDrafts] = useState({});

  const handleChange = (roommateId, value) => {
    setDrafts((prev) => ({ ...prev, [roommateId]: value }));
  };

  const handleBlur = (roommateId) => {
    const value = drafts[roommateId];
    if (value === undefined) return;
    const numeric = parseFloat(value);
    if (Number.isNaN(numeric)) return;
    onUpdate(roommateId, numeric);
    setDrafts((prev) => {
      const next = { ...prev };
      delete next[roommateId];
      return next;
    });
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
            const currentValue =
              drafts[row.roommate_id] !== undefined
                ? drafts[row.roommate_id]
                : row.current_reading ?? '';

            return (
              <tr key={row.roommate_id}>
                <td className="font-medium">{row.name}</td>
                <td className="text-right tabular-nums">
                  {row.previous_reading?.toLocaleString() ?? '-'}
                </td>
                <td className="text-right">
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={currentValue}
                    disabled={loading}
                    onChange={(e) => handleChange(row.roommate_id, e.target.value)}
                    onBlur={() => handleBlur(row.roommate_id)}
                    className="w-32 text-right"
                  />
                </td>
                <td className="text-right tabular-nums">
                  {row.sub_units?.toLocaleString(undefined, { maximumFractionDigits: 2 }) ?? '-'}
                </td>
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
      </table>
    </div>
  );
}

export default ReadingsTable;
