import { useEffect, useRef, useState } from 'react';
import { voicePayment } from '../api';
import { today } from '../format';

const MAX_SECONDS = 15;
const MIN_SECONDS = 1;

// What the browser can record, in the order 60db prefers (Android/Chrome give
// WebM, iPhones MP4).
const recordingType = () =>
  ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'].find((t) =>
    window.MediaRecorder?.isTypeSupported?.(t)
  ) || '';

export const canRecord = () =>
  typeof window !== 'undefined' &&
  Boolean(window.MediaRecorder && navigator.mediaDevices?.getUserMedia);

const micError = (err) =>
  err?.name === 'NotAllowedError' || err?.name === 'SecurityError'
    ? 'Allow microphone access to add payments by voice.'
    : err?.name === 'NotFoundError'
      ? 'No microphone found.'
      : 'Couldn’t start the microphone.';

function MicIcon({ className }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" strokeLinecap="round" />
    </svg>
  );
}

// "Say it": records up to 15 s, sends it, and hands back the draft payment
// (onDraft). Saving stays with the form, so the person checks it first.
function VoicePaymentButton({ onDraft, disabled }) {
  const [state, setState] = useState('idle'); // idle | recording | sending
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState(null);
  const recorder = useRef(null);
  const timer = useRef(null);
  const started = useRef(0);
  const cancelled = useRef(false);

  const cleanup = () => {
    clearInterval(timer.current);
    recorder.current?.stream.getTracks().forEach((t) => t.stop());
  };

  // Unmounted (e.g. the tab closes mid-recording): stop the mic, drop the result.
  // Set again on mount, since React may mount, unmount and remount in development.
  useEffect(() => {
    cancelled.current = false;
    return () => {
      cancelled.current = true;
      if (recorder.current?.state === 'recording') recorder.current.stop();
      cleanup();
    };
  }, []);

  const send = async (blob) => {
    setState('sending');
    try {
      const draft = await voicePayment(blob, today());
      if (!cancelled.current) onDraft(draft);
    } catch (err) {
      if (!cancelled.current) setError(err.message);
    } finally {
      if (!cancelled.current) setState('idle');
    }
  };

  const start = async () => {
    setError(null);
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      setError(micError(err));
      return;
    }
    const type = recordingType();
    const rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    const chunks = [];
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    rec.onstop = () => {
      cleanup();
      if (cancelled.current) return;
      const length = (Date.now() - started.current) / 1000;
      if (length < MIN_SECONDS) {
        setState('idle');
        setError('That was too short. Tap the mic, say the payment, then tap Stop.');
        return;
      }
      send(new Blob(chunks, { type: rec.mimeType || type || 'audio/webm' }));
    };
    recorder.current = rec;
    started.current = Date.now();
    setSeconds(0);
    rec.start();
    setState('recording');
    timer.current = setInterval(() => {
      const s = (Date.now() - started.current) / 1000;
      setSeconds(Math.floor(s));
      if (s >= MAX_SECONDS && rec.state === 'recording') rec.stop();
    }, 250);
  };

  const stop = () => {
    if (recorder.current?.state === 'recording') recorder.current.stop();
  };

  return (
    <div className="space-y-2">
      {state === 'recording' ? (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2">
          <span className="relative flex h-3 w-3">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-rose-400 opacity-75" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-rose-500" />
          </span>
          <span className="text-sm font-medium text-rose-700 tabular-nums">
            Listening… 0:{String(seconds).padStart(2, '0')}
          </span>
          <button type="button" onClick={stop} className="btn-danger ml-auto">
            Stop
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={start}
          disabled={disabled || state === 'sending'}
          className="btn-secondary inline-flex items-center gap-2"
        >
          <MicIcon className="h-4 w-4" />
          {state === 'sending' ? 'Understanding…' : 'Say it'}
        </button>
      )}
      {state === 'recording' && (
        <p className="text-xs text-slate-500">
          e.g. “500 rupees yesterday, DG” or “kal dedh hazaar ka recharge kiya”
        </p>
      )}
      {error && <p className="text-sm text-rose-600">{error}</p>}
    </div>
  );
}

export default VoicePaymentButton;
