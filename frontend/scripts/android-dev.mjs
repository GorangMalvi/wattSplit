// npm run android:dev: the app on a connected phone or emulator, loading the
// Vite dev server on this PC, so saved changes show up on the device straight
// away (no push, no APK release).
//
// It installs "wattSplit Dev" (a debug build with its own app id, so the real
// wattSplit stays installed), points it at http://localhost:5180, maps the
// device's localhost:5180 to this PC with `adb reverse`, launches it, and
// starts Vite. API calls go through Vite's /api proxy to the local backend on
// :8000, so that has to be running too (docker compose up -d backend, or
// uvicorn).
//
//   npm run android:dev                  build, install, launch, start Vite
//   npm run android:dev -- --no-install  skip the build (only web code changed)
//
// Rebuild (the default) after native changes: Capacitor plugins, the manifest,
// build.gradle.
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { connect } from 'node:net';
import { homedir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Not 5173: docker-compose publishes the built web app there.
const PORT = 5180;
const APP_ID = 'com.gorangmalvi.wattsplit.dev';
const win = process.platform === 'win32';
const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const androidDir = join(root, 'android');
const sdk =
  process.env.ANDROID_HOME ||
  process.env.ANDROID_SDK_ROOT ||
  join(homedir(), win ? 'AppData/Local/Android/Sdk' : 'Android/Sdk');
const adb = join(sdk, 'platform-tools', win ? 'adb.exe' : 'adb');
const install = !process.argv.includes('--no-install');

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
    const res = await fetch(`http://127.0.0.1:${port}/@vite/client`);
    return res.ok;
  } catch {
    return false;
  }
};

// 1. A device to run on.
if (!existsSync(adb)) fail(`adb not found at ${adb}. Set ANDROID_HOME to your Android SDK.`);
const devices = adbOut('devices')
  .split('\n')
  .slice(1)
  .filter((line) => line.trim().endsWith('\tdevice'));
if (devices.length === 0) {
  fail('No phone or emulator connected. Start the emulator (Android Studio > Device Manager > ▶) or plug in a phone with USB debugging on.');
}
if (devices.length > 1) console.log(`Several devices connected; using ${devices[0].split('\t')[0]}.`);
const serial = devices[0].split('\t')[0];

// 2. Build and install the dev app, pointed at the dev server.
if (install) {
  if (!process.env.JAVA_HOME) fail('JAVA_HOME is not set (it should point to JDK 21).');
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

// 3. The device's localhost:5180 -> this PC's Vite (works for emulators and USB phones).
run(adb, ['-s', serial, 'reverse', `tcp:${PORT}`, `tcp:${PORT}`], { shell: false });

if (!(await portOpen(8000))) {
  console.warn(
    '\n⚠ No backend on http://127.0.0.1:8000, so the app will show API errors. Start it with:\n' +
      '    docker compose up -d backend\n' +
      '  or: cd backend && uvicorn app.main:app --reload --port 8000\n'
  );
}

// 4. Vite (unless it's already running), then open the app.
const viteRunning = await portOpen(PORT);
if (viteRunning && !(await isVite(PORT))) {
  fail(`Port ${PORT} is in use by something other than Vite. Stop it, or change PORT in scripts/android-dev.mjs.`);
}
const vite = viteRunning
  ? null
  : spawn('npx', ['vite', '--host', '127.0.0.1', '--port', String(PORT), '--strictPort'], { cwd: root, stdio: 'inherit', shell: win });
if (vite) {
  for (let i = 0; i < 60 && !(await portOpen(PORT)); i++) await new Promise((r) => setTimeout(r, 500));
}
spawnSync(adb, ['-s', serial, 'shell', 'am', 'force-stop', APP_ID]);
spawnSync(adb, ['-s', serial, 'shell', 'monkey', '-p', APP_ID, '-c', 'android.intent.category.LAUNCHER', '1'], {
  stdio: 'ignore',
});
console.log(
  `\n✓ wattSplit Dev is open on ${serial}, live from http://localhost:${PORT}. Save a file and it updates on the device.` +
    '\n  Console and errors: open chrome://inspect in Chrome on this PC.' +
    (vite ? '\n  Ctrl+C stops Vite.' : '\n  (Vite was already running.)')
);
if (vite) vite.on('exit', (code) => process.exit(code ?? 0));
