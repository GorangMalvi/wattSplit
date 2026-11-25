import { Capacitor } from '@capacitor/core';

const SITE = 'https://wattsplit.jugadu.tech';

// The privacy policy is a plain page on the website. In the Android app a
// new-tab link goes nowhere, so it opens in the phone's browser instead.
function PrivacyLink({ className = 'underline' }) {
  const open = async (e) => {
    if (!Capacitor.isNativePlatform()) return;
    e.preventDefault();
    const { Browser } = await import('@capacitor/browser');
    await Browser.open({ url: `${SITE}/privacy.html` });
  };
  return (
    <a href="/privacy.html" target="_blank" rel="noreferrer" onClick={open} className={className}>
      Privacy policy
    </a>
  );
}

export default PrivacyLink;
