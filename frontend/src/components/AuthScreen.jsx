import { useEffect, useState } from 'react';
import { devLogin, getDevLogin } from '../api';
import { supabase } from '../supabase';

// Supabase allows one code per email every 60 seconds by default.
const RESEND_SECONDS = 60;

// invite: from an invite link ({ household, roommate, email }), or null.
function AuthScreen({ invite = null }) {
  const [step, setStep] = useState('email');
  const [email, setEmail] = useState('');

  // The invite is looked up after the screen appears: fill in its email then.
  useEffect(() => {
    if (invite?.email) setEmail((current) => current || invite.email);
  }, [invite]);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [cooldown, setCooldown] = useState(0);
  // Local development only: the backend can sign in with a fixed code and
  // no email. import.meta.env.DEV is false in production builds, so this
  // check (and the dev sign-in) is left out of them.
  const [devCodeState, setDevCode] = useState(null);
  const devCode = import.meta.env.DEV ? devCodeState : null;

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    getDevLogin()
      .then((d) => setDevCode(d.enabled ? d.code : null))
      .catch(() => setDevCode(null));
  }, []);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const timer = setTimeout(() => setCooldown((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  const sendCode = async () => {
    setBusy(true);
    setError(null);
    try {
      if (import.meta.env.DEV && devCode) {
        // Dev sign-in: no email; the code is checked when it's entered.
        setStep('code');
        setCode('');
        return;
      }
      // Creates the account on first sign-in; Supabase emails a one-time code.
      const { error: err } = await supabase.auth.signInWithOtp({
        email: email.trim(),
        options: { shouldCreateUser: true },
      });
      if (err) throw err;
      setStep('code');
      setCode('');
      setCooldown(RESEND_SECONDS);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const verifyCode = async () => {
    setBusy(true);
    setError(null);
    try {
      const { error: err } = import.meta.env.DEV && devCode
        ? await supabase.auth.verifyOtp(await devLogin(email.trim(), code.trim()))
        : await supabase.auth.verifyOtp({ email: email.trim(), token: code.trim(), type: 'email' });
      if (err) throw err;
      // onAuthStateChange in Root picks up the new session.
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (step === 'email') sendCode();
    else verifyCode();
  };

  const changeEmail = () => {
    setStep('email');
    setCode('');
    setError(null);
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="card w-full max-w-sm">
        <h1 className="text-2xl font-bold text-slate-900">wattSplit</h1>
        <p className="mb-6 text-sm text-slate-500">
          {step === 'email'
            ? 'Sign in or create an account with a code sent to your email.'
            : devCode
              ? `Dev sign-in for ${email.trim()}: no email is sent.`
              : `Enter the code we sent to ${email.trim()}.`}
        </p>

        {devCode && (
          <div className="-mt-2 mb-5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            Local development: sign in with code <span className="font-mono font-semibold">{devCode}</span>.
          </div>
        )}

        {invite && (
          <div className="-mt-2 mb-5 rounded-lg border border-indigo-100 bg-indigo-50 px-3 py-2 text-sm text-indigo-900">
            You're invited to join <span className="font-semibold">{invite.household}</span> as{' '}
            <span className="font-semibold">{invite.roommate}</span>. Sign in with{' '}
            <span className="font-medium">{invite.email}</span> to accept.
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {step === 'email' ? (
            <div className="flex flex-col gap-1">
              <label htmlFor="auth-email" className="text-xs font-medium text-slate-500">
                Email
              </label>
              <input
                id="auth-email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              <label htmlFor="auth-code" className="text-xs font-medium text-slate-500">
                Code
              </label>
              <input
                id="auth-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                autoFocus
                pattern="[0-9]{6,10}"
                maxLength={10}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                className="text-center font-mono text-lg tracking-[0.4em]"
              />
            </div>
          )}

          {error && <p className="text-sm text-rose-600">{error}</p>}

          <button type="submit" disabled={busy} className="btn-primary">
            {busy ? 'Please wait…' : step === 'email' ? 'Send code' : 'Verify & sign in'}
          </button>
        </form>

        {step === 'code' && !devCode && (
          <div className="mt-4 flex items-center justify-between text-sm">
            <button
              type="button"
              onClick={changeEmail}
              className="px-0 py-0 font-medium text-indigo-600 hover:underline"
            >
              Use a different email
            </button>
            <button
              type="button"
              onClick={sendCode}
              disabled={busy || cooldown > 0}
              className="px-0 py-0 font-medium text-indigo-600 hover:underline"
            >
              {cooldown > 0 ? `Resend in ${cooldown}s` : 'Resend code'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default AuthScreen;
