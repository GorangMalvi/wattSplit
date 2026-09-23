import { useState } from 'react';
import { createHousehold, joinHousehold } from '../api';

function HouseholdSetup({ onDone, onCancel, onSignOut }) {
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const run = async (action) => {
    setBusy(true);
    setError(null);
    try {
      onDone(await action());
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const handleCreate = (e) => {
    e.preventDefault();
    run(() => createHousehold(name.trim()));
  };

  const handleJoin = (e) => {
    e.preventDefault();
    run(() => joinHousehold(code.trim()));
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-2xl space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Set up your flat</h1>
          <p className="text-sm text-slate-500">
            Create a household for your flat, or join one a flatmate already created.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <form onSubmit={handleCreate} className="card flex flex-col gap-3">
            <h2 className="text-lg font-semibold text-slate-900">Create a household</h2>
            <label htmlFor="household-name" className="text-xs font-medium text-slate-500">
              Name
            </label>
            <input
              id="household-name"
              required
              maxLength={80}
              placeholder="e.g. Golf Flat 1"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <button type="submit" disabled={busy || !name.trim()} className="btn-primary">
              Create
            </button>
          </form>

          <form onSubmit={handleJoin} className="card flex flex-col gap-3">
            <h2 className="text-lg font-semibold text-slate-900">Join with a code</h2>
            <label htmlFor="invite-code" className="text-xs font-medium text-slate-500">
              Household code, or the personal invite code from your email
            </label>
            <input
              id="invite-code"
              required
              maxLength={16}
              placeholder="e.g. K7Q2M9XD"
              value={code}
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              className="uppercase tracking-widest"
            />
            <button type="submit" disabled={busy || !code.trim()} className="btn-primary">
              Join
            </button>
          </form>
        </div>

        {error && <p className="text-sm text-rose-600">{error}</p>}

        <div className="flex gap-3">
          {onCancel && (
            <button onClick={onCancel} className="btn-secondary">
              Back to dashboard
            </button>
          )}
          <button onClick={onSignOut} className="btn-secondary">
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
}

export default HouseholdSetup;
