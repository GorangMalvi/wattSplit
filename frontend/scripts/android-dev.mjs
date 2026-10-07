// The "wattSplit Dev" app on a connected emulator or phone, live from the Vite
// dev server that `npm run local` runs (it calls this script itself).
//
// It installs "wattSplit Dev" (a debug build with its own app id, so the real
// wattSplit stays installed) pointed at http://localhost:5180, maps the
// device's localhost:5180 (Vite) and :54321 (local Supabase) to this PC with
// `adb reverse`, and opens it.
//
//   npm run android:dev                  rebuild + reinstall, then open (after
//                                        native changes: plugins, manifest, gradle)
//   npm run android:dev -- --no-install  just open it again
//   --if-device                          (used by npm run local) quietly do
//                                        nothing without a device; install only
//                                        if the app is missing
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { connect } from 'node:net';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Not 5173: docker-compose publishes the built web app there.
const PORT = 5180;
const SUPABASE_PORT = 54321; // local Supabase (supabase/config.toml)
const APP_ID = 'com.gorangmalvi.wattsplit.dev';
const win = process.platform === 'win32';
const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const androidDir = join(root, 'android');
const sdk =
  process.env.ANDROID_HOME ||
  process.env.ANDROID_SDK_ROOT ||
  join(homedir(), win ? 'AppData/Local/Android/Sdk' : 'Android/Sdk');
const adb = join(sdk, 'platform-tools', win ? 'adb.exe' : 'adb');
const ifDevice = process.argv.includes('--if-device');

const fail = (message) => {
  console.error(`\n✗ ${message}`);
  process.exit(1);
};

const run = (cmd, args, opts = {}) => {
  const res = spawnSync(cmd, args, { stdio: 'inherit', shell: win, ...opts });
  if (res.status !== 0) fail(`${cmd} ${args.join(' ')} failed`);
};

const adbOut = (...args) => spawnSync(adb, args, { encoding: 'utf-8' }).stdout || '';

const portOpen = (port) =>
  new Promise((resolve) => {
    const socket = connect({ host: '127.0.0.1', port }, () => {
      socket.end();
      resolve(true);
    });
    socket.on('error', () => resolve(false));
  });

// Something on the port, and is it Vite? (Vite serves its client script.)
const isVite = async (port) => {
  try {
    return (await fetch(`http://127.0.0.1:${port}/@vite/client`)).ok;
  } catch {
    return false;
  }
};

// 1. A device to run on.
if (!existsSync(adb)) {
  if (ifDevice) process.exit(2);
  fail(`adb not found at ${adb}. Set ANDROID_HOME to your Android SDK.`);
}
const devices = adbOut('devices')
  .split('\n')
  .slice(1)
  .filter((line) => line.trim().endsWith('\tdevice'));
if (devices.length === 0) {
  if (ifDevice) process.exit(2);
  fail('No phone or emulator connected. Start the emulator (Android Studio > Device Manager > ▶) or plug in a phone with USB debugging on.');
}
if (devices.length > 1) console.log(`Several devices connected; using ${devices[0].split('\t')[0]}.`);
const serial = devices[0].split('\t')[0];

if (!(await isVite(PORT))) fail(`Nothing is serving the app on port ${PORT}. Run "npm run local" first.`);

// 2. Build and install the dev app, pointed at the dev server.
const installed = adbOut('-s', serial, 'shell', 'pm', 'list', 'packages', APP_ID).includes(`package:${APP_ID}`);
const install = ifDevice ? !installed : !process.argv.includes('--no-install');
if (install) {
  if (!process.env.JAVA_HOME) {
    // Android Studio ships a JDK; use it when JAVA_HOME isn't set.
    const studioJdk = 'C:\\Program Files\\Android\\Android Studio\\jbr';
    if (win && existsSync(studioJdk)) process.env.JAVA_HOME = studioJdk;
    else fail('JAVA_HOME is not set (it should point to JDK 21).');
  }
  process.env.ANDROID_HOME ||= sdk;
  if (!existsSync(join(root, 'dist', 'index.html'))) run('npx', ['vite', 'build'], { cwd: root });
  run('npx', ['cap', 'sync', 'android'], { cwd: root });

  // cap sync just wrote this file; the next sync (any APK build) rewrites it
  // without the dev server, so release builds are never affected.
  const configPath = join(androidDir, 'app/src/main/assets/capacitor.config.json');
  const config = JSON.parse(readFileSync(configPath, 'utf-8'));
  // Plain http is allowed by the debug-only android/app/src/debug/AndroidManifest.xml.
  config.server = { ...config.server, url: `http://localhost:${PORT}`, cleartext: true };
  writeFileSync(configPath, JSON.stringify(config, null, '\t'));

  // Full path: cmd.exe may not look in the current folder. Quoted for the
  // spaces in the path (a .bat needs the shell, which takes the string as is).
  const gradlew = join(androidDir, win ? 'gradlew.bat' : 'gradlew');
  run(win ? `"${gradlew}"` : gradlew, ['assembleDebug', '-q'], { cwd: androidDir });
  const apk = join(androidDir, 'app/build/outputs/apk/debug/app-debug.apk');
  console.log(`Installing wattSplit Dev on ${serial}…`);
  run(adb, ['-s', serial, 'install', '-r', apk], { shell: false });
}

// 3. The device's localhost:5180 (Vite) and :54321 (local Supabase sign-in)
// -> this PC. Works the same for emulators and USB phones.
for (const port of [PORT, SUPABASE_PORT]) {
  run(adb, ['-s', serial, 'reverse', `tcp:${port}`, `tcp:${port}`], { shell: false, stdio: 'ignore' });
}

// 4. Open it (restarted, so it loads the current code).
spawnSync(adb, ['-s', serial, 'shell', 'am', 'force-stop', APP_ID]);
spawnSync(adb, ['-s', serial, 'shell', 'monkey', '-p', APP_ID, '-c', 'android.intent.category.LAUNCHER', '1'], {
  stdio: 'ignore',
});
if (!ifDevice) {
  console.log(
    `\n✓ wattSplit Dev is open on ${serial}, live from http://localhost:${PORT}.` +
      '\n  Console and errors: open chrome://inspect in Chrome on this PC.'
  );
}
