import { useEffect, useState } from 'react';
import { deleteAccount, getAccount } from '../api';
import ErrorAlert from './ErrorAlert';
import LoadingSpinner from './LoadingSpinner';
import PrivacyLink from './PrivacyLink';

// Account: who you're signed in as, and deleting the account (Google Play requires it).
// onDeleted: after the account is gone (Root signs out). onBack: back to the app.
function AccountPage({ onDeleted, onBack }) {
  const [account, setAccount] = useState(null);
  const [error, setError] = useState(null);
  const [typed, setTyped] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getAccount()
      .then(setAccount)
      .catch((err) => setError(err.message));
  }, []);

  const remove = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await deleteAccount(typed.trim());
      onDeleted();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  if (!account) return error ? <ErrorAlert message={error} /> : <LoadingSpinner />;

  const blocked = account.households.filter((h) => h.blocks);
  const deleted = account.households.filter((h) => h.role === 'owner' && h.others === 0);
  const left = account.households.filter((h) => !h.blocks && !(h.role === 'owner' && h.others === 0));

  return (
    <div className="mx-auto max-w-xl space-y-6 p-4 md:p-6">
      <button onClick={onBack} className="btn-secondary">
        ← Back
      </button>
      <div className="card">
        <h2 className="text-lg font-semibold text-slate-900">Account</h2>
        <p className="mt-1 text-sm text-slate-600">
          Signed in as <span className="font-medium">{account.email}</span>
        </p>
        <p className="mt-3 text-sm">
          <PrivacyLink className="text-indigo-600 underline" />
        </p>
      </div>

      <div className="card border-rose-200">
        <h2 className="text-lg font-semibold text-rose-700">Delete my account</h2>
        <p className="mt-1 text-sm text-slate-600">
          This deletes your sign-in and email address, and removes you from your households. It can&apos;t be undone.
        </p>
        {error && (
          <div className="mt-3">
            <ErrorAlert message={error} />
          </div>
        )}
        {blocked.length > 0 ? (
          <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            You own {blocked.map((h) => h.name).join(', ')}, which other people have joined. First make one of them the
            owner (Household → Roommates → Make owner), or delete the household.
          </div>
        ) : (
          <>
            <ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-slate-700">
              {deleted.map((h) => (
                <li key={h.id}>
                  <span className="font-medium">{h.name}</span> is deleted with everything in it (you&apos;re its
                  only member).
                </li>
              ))}
              {left.map((h) => (
                <li key={h.id}>
                  You leave <span className="font-medium">{h.name}</span>. Your name, readings and payments stay there,
                  because your flatmates&apos; bills depend on them.
                </li>
              ))}
              {account.households.length === 0 && <li>You aren&apos;t in any household.</li>}
            </ul>
            <form onSubmit={remove} className="mt-4 flex flex-wrap items-end gap-3">
              <div className="flex flex-col gap-1">
                <label htmlFor="delete-account-confirm" className="text-xs font-medium text-slate-500">
                  Type DELETE to confirm
                </label>
                <input
                  id="delete-account-confirm"
                  autoComplete="off"
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                />
              </div>
              <button type="submit" disabled={busy || typed.trim() !== 'DELETE'} className="btn-danger">
                {busy ? 'Deleting…' : 'Delete my account'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

export default AccountPage;
