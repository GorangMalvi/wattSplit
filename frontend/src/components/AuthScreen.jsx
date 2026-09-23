import { useEffect, useState } from 'react';
import { supabase } from '../supabase';

// Supabase allows one code per email every 60 seconds by default.
const RESEND_SECONDS = 60;

function AuthScreen() {
  const [step, setStep] = useState('email');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [cooldown, setCooldown] = useState(0);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const timer = setTimeout(() => setCooldown((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  const sendCode = async () => {
    setBusy(true);
    setError(null);
    try {
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
      const { error: err } = await supabase.auth.verifyOtp({
        email: email.trim(),
        token: code.trim(),
        type: 'email',
      });
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
            : `Enter the code we sent to ${email.trim()}.`}
        </p>

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

        {step === 'code' && (
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
