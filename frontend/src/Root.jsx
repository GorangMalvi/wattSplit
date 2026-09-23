import { useEffect, useState } from 'react';
import App from './App';
import { getHouseholds, setActiveHousehold } from './api';
import AuthScreen from './components/AuthScreen';
import ErrorAlert from './components/ErrorAlert';
import HouseholdSetup from './components/HouseholdSetup';
import LoadingSpinner from './components/LoadingSpinner';
import { supabase, supabaseConfigured } from './supabase';

const HOUSEHOLD_KEY = 'wattsplit.household';

function readStoredHousehold() {
  try {
    return localStorage.getItem(HOUSEHOLD_KEY);
  } catch {
    return null;
  }
}

function storeHousehold(id) {
  try {
    localStorage.setItem(HOUSEHOLD_KEY, id);
  } catch {
    // Storage unavailable (private mode etc.): just don't remember it.
  }
}

function CenteredMessage({ children }) {
  return <div className="flex min-h-screen items-center justify-center p-4">{children}</div>;
}

function Root() {
  // undefined = still checking for an existing session.
  const [session, setSession] = useState(undefined);
  const [households, setHouseholds] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [addingHousehold, setAddingHousehold] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!supabase) return undefined;
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next));
    return () => data.subscription.unsubscribe();
  }, []);

  const userId = session?.user?.id;

  useEffect(() => {
    setHouseholds(null);
    setError(null);
    if (!userId) return;
    getHouseholds()
      .then((list) => {
        setHouseholds(list);
        const stored = readStoredHousehold();
        setActiveId(list.some((h) => h.id === stored) ? stored : list[0]?.id ?? null);
      })
      .catch((err) => setError(err.message));
  }, [userId]);

  const selectHousehold = (id) => {
    storeHousehold(id);
    setActiveId(id);
    setAddingHousehold(false);
  };

  const handleHouseholdReady = (household) => {
    setHouseholds((prev) =>
      prev.some((h) => h.id === household.id) ? prev : [...prev, household]
    );
    selectHousehold(household.id);
  };

  const signOut = () => supabase.auth.signOut();

  const copyInvite = async (code) => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked: the code is visible on screen anyway.
    }
  };

  if (!supabaseConfigured) {
    return (
      <CenteredMessage>
        <ErrorAlert message="Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY in .env and rebuild." />
      </CenteredMessage>
    );
  }

  if (session === undefined) return <LoadingSpinner />;
  if (!session) return <AuthScreen />;

  if (error) {
    return (
      <CenteredMessage>
        <ErrorAlert message={error} onRetry={() => window.location.reload()} />
      </CenteredMessage>
    );
  }

  if (households === null) return <LoadingSpinner />;

  const active = households.find((h) => h.id === activeId);

  if (!active || addingHousehold) {
    return (
      <HouseholdSetup
        onDone={handleHouseholdReady}
        onCancel={active ? () => setAddingHousehold(false) : null}
        onSignOut={signOut}
      />
    );
  }

  // Set before App's effects run so every request carries this household.
  setActiveHousehold(active.id);

  return (
    <>
      <div className="border-b border-slate-200 bg-white px-4 py-3 md:px-6 lg:px-8">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-lg font-bold text-indigo-600">wattSplit</span>
            <select
              aria-label="Household"
              value={active.id}
              onChange={(e) =>
                e.target.value === '__add__'
                  ? setAddingHousehold(true)
                  : selectHousehold(e.target.value)
              }
            >
              {households.map((h) => (
                <option key={h.id} value={h.id}>
                  {h.name}
                </option>
              ))}
              <option value="__add__">+ Create or join another…</option>
            </select>
            <button
              onClick={() => copyInvite(active.invite_code)}
              className="btn-secondary"
              title="Share this code so flatmates can join"
            >
              Invite code: <span className="font-mono tracking-widest">{active.invite_code}</span>
              {copied && <span className="ml-2 text-emerald-600">Copied</span>}
            </button>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-500">{session.user.email}</span>
            <button onClick={signOut} className="btn-secondary">
              Sign out
            </button>
          </div>
        </div>
      </div>
      <App key={active.id} />
    </>
  );
}

export default Root;
