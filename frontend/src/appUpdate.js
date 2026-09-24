// In-app update check for the Android app: compares this build's version with
// the latest GitHub release. Android never lets a sideloaded app install itself,
// so the user taps Update, the APK downloads, and Android asks to install it.

export const APP_VERSION = import.meta.env.VITE_APP_VERSION || '0.0.0';

const LATEST_RELEASE_API = 'https://api.github.com/repos/GorangMalvi/wattSplit/releases/latest';
// Every release attaches the APK as plain wattSplit.apk too, so this link always works.
export const LATEST_APK_URL = 'https://github.com/GorangMalvi/wattSplit/releases/latest/download/wattSplit.apk';

const parse = (version) => {
  const match = String(version).trim().replace(/^v/i, '').match(/^(\d+)\.(\d+)\.(\d+)/);
  return match ? match.slice(1).map(Number) : null;
};

// True when `latest` is a higher x.y.z than `current`; unparseable versions never are.
export function isNewer(latest, current) {
  const [a, b] = [parse(latest), parse(current)];
  if (!a || !b) return false;
  for (let i = 0; i < 3; i += 1) {
    if (a[i] !== b[i]) return a[i] > b[i];
  }
  return false;
}

// { version, notes } when GitHub has a newer release with the APK attached, else null.
// Any failure (offline, rate limit) just means no banner.
export async function checkForUpdate() {
  try {
    const res = await fetch(LATEST_RELEASE_API, { headers: { Accept: 'application/vnd.github+json' } });
    if (!res.ok) return null;
    const release = await res.json();
    const hasApk = (release.assets || []).some((a) => a.name === 'wattSplit.apk');
    if (!hasApk || release.draft || release.prerelease) return null;
    const version = String(release.tag_name || '').replace(/^v/i, '');
    return isNewer(version, APP_VERSION) ? { version, url: release.html_url } : null;
  } catch {
    return null;
  }
}
