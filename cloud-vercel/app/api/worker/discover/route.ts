import { NextRequest, NextResponse } from "next/server";
import { randomBytes } from "crypto";
import { isWorker } from "@/lib/auth";
import { getSettings, initDb, q } from "@/lib/db";
export const dynamic = "force-dynamic";

/** Worker offers candidate trending videos; unseen ones enqueue as
 *  auto jobs up to the daily cap. */
export async function POST(req: NextRequest) {
  if (!isWorker(req)) return NextResponse.json({ detail: "bad worker token" }, { status: 401 });
  await initDb();
  const settings = await getSettings();
  if (settings.auto_enabled !== "1") return NextResponse.json({ enqueued: 0, reason: "auto mode off" });
  const body = await req.json().catch(() => ({}));
  const videos: any[] = body.videos || [];
  const cap = parseInt(settings.daily_auto_cap || "5", 10);
  const today = new Date().toISOString().slice(0, 10);
  const autoRows = await q(`SELECT created_at FROM jobs WHERE kind='auto'`);
  const madeToday = autoRows.filter(
    (r) => new Date(r.created_at * 1000).toISOString().slice(0, 10) === today).length;
  let enqueued = 0;
  const now = Date.now() / 1000;
  for (const v of videos) {
    if (madeToday + enqueued >= cap) break;
    const vid = String(v.video_id || "").trim();
    const url = String(v.url || "").trim();
    if (!vid || !url) continue;
    const seen = await q(`SELECT video_id FROM seen WHERE video_id=$1`, [vid]);
    if (seen.length) continue;
    await q(`INSERT INTO seen (video_id, title, at) VALUES ($1, $2, $3)`,
      [vid, String(v.title || "").slice(0, 200), now]);
    await q(
      `INSERT INTO jobs (id, kind, source_url, title, status, stage, message,
         clips, auto_upload, created_at, updated_at, claimed_by, video_id)
       VALUES ($1, 'auto', $2, $3, 'queued', 'waiting',
         'auto-discovered (trending)', '[]', 1, $4, $4, NULL, $5)`,
      [randomBytes(6).toString("hex"), url, String(v.title || "").slice(0, 200), now, vid]);
    enqueued++;
  }
  return NextResponse.json({ enqueued });
}
