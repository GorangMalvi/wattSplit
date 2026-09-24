import { Capacitor } from '@capacitor/core';
import { useEffect, useState } from 'react';
import { APP_VERSION, LATEST_APK_URL, checkForUpdate } from '../appUpdate';

// Android app only (the website is always the latest): "Update available"
// when GitHub has a newer release. "Later" hides it until the next launch.
function UpdateBanner({ enabled = Capacitor.isNativePlatform() }) {
  const [update, setUpdate] = useState(null);
  const [opening, setOpening] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    checkForUpdate().then(setUpdate);
  }, [enabled]);

  if (!update) return null;

  const download = async () => {
    setOpening(true);
    try {
      // The phone's browser downloads the APK, then Android offers to install it.
      const { Browser } = await import('@capacitor/browser');
      await Browser.open({ url: LATEST_APK_URL });
    } catch {
      window.open(LATEST_APK_URL, '_blank');
    } finally {
      setOpening(false);
    }
  };

  return (
    <div className="bg-indigo-600 px-4 py-2 text-sm text-white md:px-6 lg:px-8" role="status">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2">
        <span>
          <span className="font-semibold">Update available: v{update.version}</span>
          <span className="opacity-80"> (you have v{APP_VERSION})</span>
        </span>
        <span className="flex gap-2">
          <button
            onClick={download}
            disabled={opening}
            className="bg-white px-3 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-50"
          >
            {opening ? 'Opening…' : 'Update'}
          </button>
          <button
            onClick={() => setUpdate(null)}
            className="px-3 py-1 text-xs text-white/90 underline hover:text-white"
          >
            Later
          </button>
        </span>
      </div>
    </div>
  );
}

export default UpdateBanner;
