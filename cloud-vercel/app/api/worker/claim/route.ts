import { NextRequest, NextResponse } from "next/server";
import { isWorker } from "@/lib/auth";
import { getSettings, initDb, jobOut, q, requeueStale, touchWorker } from "@/lib/db";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!isWorker(req)) return NextResponse.json({ detail: "bad worker token" }, { status: 401 });
  await initDb();
  const body = await req.json().catch(() => ({}));
  const wid = String(body.worker_id || "laptop");
  await touchWorker(wid);
  await requeueStale();
  const settings = await getSettings();
  const rows = await q(
    `SELECT * FROM jobs WHERE status='queued'
     ORDER BY (kind='manual') DESC, created_at ASC LIMIT 1`);
  if (!rows.length) return NextResponse.json({ job: null, settings });
  const now = Date.now() / 1000;
  await q(`UPDATE jobs SET status='claimed', claimed_by=$1, stage='claimed',
           updated_at=$2 WHERE id=$3`, [wid, now, rows[0].id]);
  const fresh = await q(`SELECT * FROM jobs WHERE id=$1`, [rows[0].id]);
  return NextResponse.json({ job: jobOut(fresh[0]), settings });
}
