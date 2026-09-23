import { useEffect, useState } from 'react';
import App from './App';
import { acceptInvite, getHouseholds, lookupInvite, setActiveHousehold } from './api';
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

const INVITE_KEY = 'wattsplit.invite';

// ?invite=CODE from an invite link. Kept in storage until it's used, because
// signing in comes first; removed from the address bar straight away.
function takeInviteCode() {
  let fromUrl = null;
  try {
    const params = new URLSearchParams(window.location.search);
    fromUrl = params.get('invite');
    if (fromUrl) {
      params.delete('invite');
      const query = params.toString();
      window.history.replaceState(
        null,
        '',
        window.location.pathname + (query ? `?${query}` : '') + window.location.hash
      );
      localStorage.setItem(INVITE_KEY, fromUrl);
    }
    return fromUrl || localStorage.getItem(INVITE_KEY);
  } catch {
    return fromUrl;
  }
}

function clearInviteCode() {
  try {
    localStorage.removeItem(INVITE_KEY);
  } catch {
    // Nothing stored.
  }
}

function CenteredMessage({ children }) {
  return <div className="flex min-h-screen items-center justify-center p-4">{children}</div>;
}

function Notice({ notice, onClose }) {
  if (!notice) return null;
  const tone =
    notice.tone === 'success'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
      : 'border-rose-200 bg-rose-50 text-rose-800';
  return (
    <div className="px-4 pt-3 md:px-6 lg:px-8">
      <div
        className={`mx-auto flex max-w-7xl items-center justify-between gap-3 rounded-lg border px-4 py-2 text-sm ${tone}`}
      >
        <span>{notice.text}</span>
        <button onClick={onClose} className="px-2 py-0 text-xs underline">
          Dismiss
        </button>
      </div>
    </div>
  );
}

function Root() {
  // undefined = still checking for an existing session.
  const [session, setSession] = useState(undefined);
  const [households, setHouseholds] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const [addingHousehold, setAddingHousehold] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(null);
  // Invite link: its code, who it's for (shown before sign-in), and the outcome.
  const [inviteCode, setInviteCode] = useState(takeInviteCode);
  const [invite, setInvite] = useState(null);
  const [notice, setNotice] = useState(null);

  const dropInvite = () => {
    clearInviteCode();
    setInviteCode(null);
    setInvite(null);
  };

  useEffect(() => {
    if (!inviteCode) return;
    lookupInvite(inviteCode)
      .then(setInvite)
      .catch((err) => {
        dropInvite();
        setNotice({ tone: 'error', text: err.message });
      });
  }, [inviteCode]); // eslint-disable-line react-hooks/exhaustive-deps

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
    (async () => {
      // Signed in with an invite pending: accept it first, then open that household.
      if (inviteCode) {
        try {
          const joined = await acceptInvite(inviteCode);
          storeHousehold(joined.id);
          try {
            localStorage.setItem('wattsplit.view', 'mine');
          } catch {
            // Storage unavailable: App opens on its default tab.
          }
          setNotice({ tone: 'success', text: `You've joined ${joined.name}. Welcome!` });
          dropInvite();
        } catch (err) {
          setNotice({ tone: 'error', text: err.message });
          // Signed in with a different email: keep the invite for the right account.
          if (err.status !== 403) dropInvite();
        }
      }
      const list = await getHouseholds();
      setHouseholds(list);
      const stored = readStoredHousehold();
      setActiveId(list.some((h) => h.id === stored) ? stored : list[0]?.id ?? null);
    })().catch((err) => setError(err.message));
  }, [userId]); // eslint-disable-line react-hooks/exhaustive-deps

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
  if (!session) {
    return (
      <>
        <Notice notice={notice} onClose={() => setNotice(null)} />
        <AuthScreen invite={invite} />
      </>
    );
  }

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
      <>
        <Notice notice={notice} onClose={() => setNotice(null)} />
        <HouseholdSetup
          onDone={handleHouseholdReady}
          onCancel={active ? () => setAddingHousehold(false) : null}
          onSignOut={signOut}
        />
      </>
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
      <Notice notice={notice} onClose={() => setNotice(null)} />
      <App key={active.id} />
    </>
  );
}

export default Root;
