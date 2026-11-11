import { NextRequest, NextResponse } from "next/server";
import { isAuthed } from "@/lib/auth";
import { WORKER_ONLINE_SECONDS, getSettings, initDb, jobOut, q, requeueStale } from "@/lib/db";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  if (!isAuthed(req)) return NextResponse.json({ detail: "login required" }, { status: 401 });
  try {
    return await handle();
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message || e) }, { status: 500 });
  }
}

async function handle() {
  await initDb();
  await requeueStale();
  const settings = await getSettings();
  const jobs = (await q(`SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100`)).map(jobOut);
  const workers = await q(`SELECT * FROM workers ORDER BY last_seen DESC`);
  const now = Date.now() / 1000;
  return NextResponse.json({
    settings, jobs,
    worker_online: workers.some((w) => now - (w.last_seen || 0) < WORKER_ONLINE_SECONDS),
    workers: workers.map((w) => ({
      id: w.id, last_seen: w.last_seen, ago_sec: Math.round(now - (w.last_seen || now)),
    })),
  });
}
