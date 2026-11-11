/**
 * Storage for the cloud control plane.
 *
 * Production (Vercel): Neon Postgres via DATABASE_URL (serverless HTTP
 * driver — no connection pooling headaches, no daily command caps).
 * Local dev/test: built-in node:sqlite file, same SQL ($n placeholders
 * are translated to ?). Tables and behaviour mirror cloud/app.py.
 */
export type Row = Record<string, any>;

const DATABASE_URL = process.env.DATABASE_URL || "";

let _sqlite: any = null;

/** Neon over its plain HTTPS query endpoint — no driver-version traps:
 *  POST https://<host>/sql  {query, params}  with the connection string
 *  in the Neon-Connection-String header. $n placeholders natively. */
async function neonQuery(text: string, params: any[]): Promise<Row[]> {
  const host = new URL(DATABASE_URL).host;
  const res = await fetch(`https://${host}/sql`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Neon-Connection-String": DATABASE_URL,
    },
    body: JSON.stringify({ query: text, params }),
  });
  const data: any = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(
      `Neon DB error (${res.status}): ${data.message || JSON.stringify(data).slice(0, 200)}`);
  }
  return (data.rows || []) as Row[];
}

function sqliteDb() {
  if (!_sqlite) {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { DatabaseSync } = require("node:sqlite");
    const fs = require("fs");
    const path = require("path");
    const dir = path.join(process.cwd(), ".data");
    fs.mkdirSync(dir, { recursive: true });
    _sqlite = new DatabaseSync(path.join(dir, "cloud.db"));
  }
  return _sqlite;
}

/** Run a query with $1..$n placeholders; returns rows (SELECT) or []. */
export async function q(text: string, params: any[] = []): Promise<Row[]> {
  if (!DATABASE_URL && process.env.VERCEL) {
    throw new Error(
      "DATABASE_URL set nahi hai — Vercel project ke Environment Variables me " +
      "Neon Postgres ka connection string daalo, phir redeploy karo.");
  }
  if (DATABASE_URL) {
    return neonQuery(text, params);
  }
  const db = sqliteDb();
  const sql = text.replace(/\$\d+/g, "?");
  const head = text.trimStart().slice(0, 6).toUpperCase();
  if (head.startsWith("SELECT")) {
    return db.prepare(sql).all(...params) as Row[];
  }
  db.prepare(sql).run(...params);
  return [];
}

const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)`,
  `CREATE TABLE IF NOT EXISTS jobs (
     id TEXT PRIMARY KEY, kind TEXT, source_url TEXT, title TEXT,
     status TEXT, stage TEXT, message TEXT, clips TEXT,
     auto_upload INTEGER, created_at DOUBLE PRECISION,
     updated_at DOUBLE PRECISION, claimed_by TEXT, video_id TEXT)`,
  `CREATE TABLE IF NOT EXISTS seen (
     video_id TEXT PRIMARY KEY, title TEXT, at DOUBLE PRECISION)`,
  `CREATE TABLE IF NOT EXISTS workers (
     id TEXT PRIMARY KEY, last_seen DOUBLE PRECISION, info TEXT)`,
];

export const DEFAULT_SETTINGS: Record<string, string> = {
  auto_enabled: "0",
  niches: "funny storytelling podcast\nmotivation speech hindi\ntech explained",
  channels: "",
  clips_per_video: "3",
  upload_privacy: "unlisted",
  min_duration: "240",
  daily_auto_cap: "5",
};

let _initPromise: Promise<void> | null = null;

export function initDb(): Promise<void> {
  if (!_initPromise) {
    _initPromise = (async () => {
      for (const stmt of SCHEMA) await q(stmt);
      for (const [k, v] of Object.entries(DEFAULT_SETTINGS)) {
        const rows = await q(`SELECT v FROM kv WHERE k=$1`, [k]);
        if (!rows.length) await q(`INSERT INTO kv (k, v) VALUES ($1, $2)`, [k, v]);
      }
    })();
  }
  return _initPromise;
}

export async function getSettings(): Promise<Record<string, string>> {
  const out = { ...DEFAULT_SETTINGS };
  for (const row of await q(`SELECT k, v FROM kv`)) out[row.k] = row.v;
  return out;
}

export function jobOut(row: Row): Row {
  const r = { ...row };
  try {
    r.clips = JSON.parse(r.clips || "[]");
  } catch {
    r.clips = [];
  }
  r.auto_upload = !!r.auto_upload;
  return r;
}

export const STALE_SECONDS = 600;
export const WORKER_ONLINE_SECONDS = 120;

export async function requeueStale(): Promise<void> {
  const cutoff = Date.now() / 1000 - STALE_SECONDS;
  await q(
    `UPDATE jobs SET status='queued', claimed_by=NULL, stage='waiting',
       message='worker offline — queue me wapas'
     WHERE status IN ('claimed','processing') AND updated_at < $1`,
    [cutoff],
  );
}

export async function touchWorker(workerId: string, info = ""): Promise<void> {
  await q(
    `INSERT INTO workers (id, last_seen, info) VALUES ($1, $2, $3)
     ON CONFLICT(id) DO UPDATE SET last_seen=EXCLUDED.last_seen, info=EXCLUDED.info`,
    [workerId, Date.now() / 1000, String(info).slice(0, 200)],
  );
}
