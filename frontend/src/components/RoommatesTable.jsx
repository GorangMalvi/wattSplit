import { useState } from 'react';

const currentMonth = () => new Date().toISOString().slice(0, 7);

function RoommatesTable({ roommates, onAdd, onUpdate, loading }) {
  const [newRoommate, setNewRoommate] = useState({ name: '', join_date: currentMonth() });

  const save = (roommate, changes) => {
    onUpdate(roommate.id, {
      name: roommate.name,
      join_date: roommate.join_date,
      leave_date: roommate.leave_date,
      is_active: roommate.is_active,
      ...changes,
    });
  };

  const addNew = () => {
    const name = newRoommate.name.trim();
    if (!name) return;
    onAdd({ name, join_date: newRoommate.join_date, leave_date: '', is_active: true });
    setNewRoommate({ name: '', join_date: currentMonth() });
  };

  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Joined</th>
            <th>Left</th>
            <th className="text-center">Active</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200">
          {roommates.map((rm) => (
            <tr key={rm.id}>
              <td className="font-medium">{rm.name}</td>
              <td>
                <input
                  type="month"
                  value={rm.join_date || ''}
                  disabled={loading}
                  onChange={(e) => save(rm, { join_date: e.target.value })}
                />
              </td>
              <td>
                <input
                  type="month"
                  value={rm.leave_date || ''}
                  disabled={loading}
                  onChange={(e) => save(rm, { leave_date: e.target.value })}
                />
              </td>
              <td className="text-center">
                <input
                  type="checkbox"
                  aria-label={`${rm.name} is active`}
                  checked={rm.is_active}
                  disabled={loading}
                  onChange={(e) => save(rm, { is_active: e.target.checked })}
                  className="h-4 w-4"
                />
              </td>
            </tr>
          ))}
          <tr>
            <td>
              <input
                placeholder="Roommate name"
                value={newRoommate.name}
                disabled={loading}
                onChange={(e) => setNewRoommate({ ...newRoommate, name: e.target.value })}
                onKeyDown={(e) => e.key === 'Enter' && addNew()}
              />
            </td>
            <td>
              <input
                type="month"
                value={newRoommate.join_date}
                disabled={loading}
                onChange={(e) => setNewRoommate({ ...newRoommate, join_date: e.target.value })}
              />
            </td>
            <td />
            <td className="text-center">
              <button
                onClick={addNew}
                disabled={loading || !newRoommate.name.trim()}
                className="btn-primary"
              >
                Add
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export default RoommatesTable;
