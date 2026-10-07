// npm run local: wattSplit entirely on this PC, for testing changes before
// they go live. Nothing here reaches the live database or sends real email.
//
//   Local Supabase (Docker, supabase/config.toml): its own Postgres + Auth;
//     emails land in a local inbox, never sent.
//   Backend:  uvicorn on 127.0.0.1:8001, pointed at local Supabase only.
//   Web app:  Vite on http://localhost:5180 with live reload.
//   Android:  if an emulator/phone is connected, "wattSplit Dev" opens on it,
//             live from the same Vite (see android-dev.mjs).
//   Sign in:  any email, code 123456 (no email at all).
//
// Ctrl+C stops the backend and Vite; local Supabase keeps running (and keeps
// its data). Stop it with: npx supabase stop --workdir ..
import { spawn, spawnSync } from 'node:child_process';
import { connect } from 'node:net';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const win = process.platform === 'win32';
const frontend = join(dirname(fileURLToPath(import.meta.url)), '..');
const repo = join(frontend, '..');
const backendDir = join(repo, 'backend');
const WEB_PORT = 5180;
const API_PORT = 8001; // not 8000: docker compose's backend (live settings) uses that
// With shell: true (needed for npx on Windows) arguments are joined into one
// command line, so the folder (it has spaces) must be quoted.
const workdir = win ? `"${repo}"` : repo;

const fail = (message) => {
  console.error(`\n✗ ${message}`);
  process.exit(1);
};

const portOpen = (port) =>
  new Promise((resolve) => {
    const socket = connect({ host: '127.0.0.1', port }, () => {
      socket.end();
      resolve(true);
    });
    socket.on('error', () => resolve(false));
  });

const waitForPort = async (port, seconds) => {
  for (let i = 0; i < seconds * 2; i++) {
    if (await portOpen(port)) return true;
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
};

const supabase = (...args) =>
  spawnSync('npx', ['supabase', ...args, '--workdir', workdir], { cwd: frontend, shell: win, encoding: 'utf-8' });

for (const port of [WEB_PORT, API_PORT]) {
  if (await portOpen(port)) fail(`Port ${port} is already in use. Is npm run local already running?`);
}

// 1. Local Supabase (the first start downloads its Docker images).
console.log('Starting local Supabase…');
const started = spawnSync('npx', ['supabase', 'start', '--workdir', workdir], {
  cwd: frontend,
  shell: win,
  stdio: ['ignore', 'ignore', 'inherit'],
});
if (started.status !== 0) fail('Local Supabase did not start. Is Docker Desktop running?');
const status = supabase('status', '-o', 'env');
const sb = Object.fromEntries(
  (status.stdout || '')
    .split('\n')
    .map((line) => line.trim().match(/^([A-Z_]+)="?(.*?)"?$/))
    .filter(Boolean)
    .map((m) => [m[1], m[2]])
);
for (const key of ['API_URL', 'ANON_KEY', 'SERVICE_ROLE_KEY', 'DB_URL', 'JWT_SECRET']) {
  if (!sb[key]) fail(`Couldn't read ${key} from "supabase status".`);
}

// Settings for the local backend. They take precedence over .env (python-dotenv
// never overrides variables that are already set), so the live database,
// Supabase project and email service in .env are not used.
const backendEnv = {
  ...process.env,
  SUPABASE_URL: sb.API_URL,
  SUPABASE_ANON_KEY: sb.ANON_KEY,
  SUPABASE_JWT_SECRET: sb.JWT_SECRET,
  SUPABASE_SERVICE_ROLE_KEY: sb.SERVICE_ROLE_KEY, // local throwaway key
  DATABASE_URL: sb.DB_URL,
  DEV_LOGIN_EMAILS: '*',
  MAILTRAP_API_TOKEN: '', // invite emails: not sent locally (the app shows the link)
  APP_URL: `http://localhost:${WEB_PORT}`,
  CORS_ORIGINS: `http://localhost:${WEB_PORT},http://127.0.0.1:${WEB_PORT}`,
  PYTHONUNBUFFERED: '1',
};

// 2. wattSplit's tables in the local database (safe to re-run).
const schema = spawnSync('python', ['-m', 'app.init_schema'], { cwd: backendDir, env: backendEnv, encoding: 'utf-8' });
if (schema.status !== 0) fail('Applying backend/app/schema.sql to the local database failed.');
console.log('Local database ready (schema.sql applied).');

// 3. Backend and Vite.
const children = [];
const start = (name, cmd, args, opts) => {
  const child = spawn(cmd, args, { stdio: 'inherit', ...opts });
  child.on('exit', (code) => {
    console.log(`\n${name} stopped${code ? ` (exit ${code})` : ''}.`);
    children.forEach((c) => c !== child && c.kill());
    process.exit(code ?? 0);
  });
  children.push(child);
};
start('Backend', 'python', ['-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', String(API_PORT)], {
  cwd: backendDir,
  env: backendEnv,
});
start('Vite', 'npx', ['vite', '--host', '127.0.0.1', '--port', String(WEB_PORT), '--strictPort'], {
  cwd: frontend,
  shell: win,
  env: {
    ...process.env,
    VITE_SUPABASE_URL: sb.API_URL,
    VITE_SUPABASE_ANON_KEY: sb.ANON_KEY,
    API_PROXY_TARGET: `http://127.0.0.1:${API_PORT}`,
  },
});
process.on('SIGINT', () => children.forEach((c) => c.kill()));

if (!(await waitForPort(API_PORT, 60))) fail('The backend did not start (see the errors above).');
if (!(await waitForPort(WEB_PORT, 60))) fail('Vite did not start (see the errors above).');

// 4. The Android dev app, if a device is connected.
const android = spawnSync('node', [join(frontend, 'scripts', 'android-dev.mjs'), '--if-device'], {
  cwd: frontend,
  stdio: 'inherit',
  env: process.env,
});

console.log(`
✓ wattSplit is running locally. Nothing here touches the live app.

  Web app      http://localhost:${WEB_PORT}
  Sign in      any email, code 123456 (no email is sent)
  Data         ${sb.STUDIO_URL || 'http://127.0.0.1:54323'}   (Supabase Studio: the local tables)
  Email inbox  ${sb.MAILPIT_URL || sb.INBUCKET_URL || 'http://127.0.0.1:54324'}   (what Supabase would have emailed)
  ${android.status === 0 ? 'Android      "wattSplit Dev" is open on the emulator' : 'Android      start an emulator, then: npm run android:dev'}

  Save a file and the web app and the emulator update. Ctrl+C stops the backend and Vite.
`);
