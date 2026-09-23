import { useState } from 'react';
import { today } from '../format';
import MeterBadge, { METERS } from './MeterBadge';

// canEdit(roommateId): whether this user may add/change that roommate's payments.
function RechargesTable({ recharges, roommates, month, onSave, onDelete, loading, canEdit = () => true }) {
  const editable = roommates.filter((rm) => canEdit(rm.id));
  // With a single choice (a member's own roommate) there's nothing to pick.
  const defaultRoommate = editable.length === 1 ? editable[0].id : '';
  const [newRecharge, setNewRecharge] = useState({
    date: today(),
    roommate_id: defaultRoommate,
    amount: '',
    notes: '',
    meter: 'main',
  });

  const [editing, setEditing] = useState({});

  const roommateName = (id) => roommates.find((r) => r.id === id)?.name || 'Unknown';

  const startEdit = (recharge) => {
    setEditing({
      ...recharge,
      amount: recharge.amount?.toString() ?? '',
    });
  };

  const cancelEdit = () => setEditing({});

  const commitEdit = () => {
    const amount = parseFloat(editing.amount);
    if (!editing.roommate_id || Number.isNaN(amount) || amount <= 0) return;
    onSave({
      id: editing.id,
      date: editing.date,
      roommate_id: editing.roommate_id,
      amount,
      notes: editing.notes,
      meter: editing.meter,
    });
    setEditing({});
  };

  const addNew = () => {
    const amount = parseFloat(newRecharge.amount);
    if (!newRecharge.roommate_id || Number.isNaN(amount) || amount <= 0) return;
    onSave({
      date: newRecharge.date,
      roommate_id: newRecharge.roommate_id,
      amount,
      notes: newRecharge.notes,
      meter: newRecharge.meter,
      month,
    });
    setNewRecharge({
      date: today(),
      roommate_id: defaultRoommate,
      amount: '',
      notes: '',
      meter: newRecharge.meter,
    });
  };

  const isEditing = (id) => editing.id === id;

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Roommate</th>
            <th className="text-right">Amount</th>
            <th>Meter</th>
            <th>Notes</th>
            <th className="text-center">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200">
          {recharges.map((r) =>
            isEditing(r.id) ? (
              <tr key={r.id} className="bg-indigo-50/50">
                <td>
                  <input
                    type="date"
                    value={editing.date}
                    onChange={(e) => setEditing({ ...editing, date: e.target.value })}
                  />
                </td>
                <td>
                  <select
                    value={editing.roommate_id}
                    onChange={(e) => setEditing({ ...editing, roommate_id: e.target.value })}
                  >
                    <option value="" disabled>
                      Select
                    </option>
                    {editable.map((rm) => (
                      <option key={rm.id} value={rm.id}>
                        {rm.name}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={editing.amount}
                    onChange={(e) => setEditing({ ...editing, amount: e.target.value })}
                    className="w-28 text-right"
                  />
                </td>
                <td>
                  <select
                    aria-label="Meter"
                    value={editing.meter || 'main'}
                    onChange={(e) => setEditing({ ...editing, meter: e.target.value })}
                  >
                    {METERS.map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    type="text"
                    value={editing.notes || ''}
                    onChange={(e) => setEditing({ ...editing, notes: e.target.value })}
                    className="w-full"
                  />
                </td>
                <td className="text-center">
                  <button onClick={commitEdit} className="btn-primary mr-2 text-xs">
                    Save
                  </button>
                  <button onClick={cancelEdit} className="btn-secondary text-xs">
                    Cancel
                  </button>
                </td>
              </tr>
            ) : (
              <tr key={r.id}>
                <td>{r.date}</td>
                <td className="font-medium">{roommateName(r.roommate_id)}</td>
                <td className="text-right tabular-nums">
                  ₹{r.amount?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                </td>
                <td>
                  <MeterBadge meter={r.meter} />
                </td>
                <td className="text-slate-500">{r.notes || '-'}</td>
                <td className="text-center">
                  {canEdit(r.roommate_id) && (
                    <>
                      <button
                        onClick={() => startEdit(r)}
                        disabled={loading}
                        className="btn-secondary mr-2 text-xs"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => onDelete(r.id)}
                        disabled={loading}
                        className="btn-danger text-xs"
                      >
                        Delete
                      </button>
                    </>
                  )}
                </td>
              </tr>
            )
          )}

          {/* Add new recharge row */}
          {editable.length > 0 && (
            <tr className="bg-slate-50/80">
              <td>
                <input
                  type="date"
                  value={newRecharge.date}
                  onChange={(e) => setNewRecharge({ ...newRecharge, date: e.target.value })}
                />
              </td>
              <td>
                <select
                  value={newRecharge.roommate_id}
                  onChange={(e) =>
                    setNewRecharge({ ...newRecharge, roommate_id: e.target.value })
                  }
                >
                  <option value="" disabled>
                    Select roommate
                  </option>
                  {editable.map((rm) => (
                    <option key={rm.id} value={rm.id}>
                      {rm.name}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={newRecharge.amount}
                  onChange={(e) =>
                    setNewRecharge({ ...newRecharge, amount: e.target.value })
                  }
                  placeholder="0.00"
                  className="w-28 text-right"
                />
              </td>
              <td>
                <select
                  aria-label="Meter"
                  value={newRecharge.meter}
                  onChange={(e) => setNewRecharge({ ...newRecharge, meter: e.target.value })}
                >
                  {METERS.map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <input
                  type="text"
                  value={newRecharge.notes}
                  onChange={(e) =>
                    setNewRecharge({ ...newRecharge, notes: e.target.value })
                  }
                  placeholder="Optional note"
                  className="w-full"
                />
              </td>
              <td className="text-center">
                <button onClick={addNew} disabled={loading} className="btn-primary text-xs">
                  Add
                </button>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default RechargesTable;
