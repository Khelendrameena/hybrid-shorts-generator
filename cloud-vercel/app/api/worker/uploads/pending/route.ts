import { NextRequest, NextResponse } from "next/server";
import { isWorker } from "@/lib/auth";
import { initDb, q } from "@/lib/db";
export const dynamic = "force-dynamic";

/** Clips jo render ho chuki hain aur scheduled YouTube upload ka
 *  wait kar rahi hain (upload_status = 'pending'), sabse purani pehle.
 *  uploaded_today = aaj (UTC) kitni clips upload ho chuki — scheduler
 *  isi count se daily limit aur next slot decide karta hai. */
export async function GET(req: NextRequest) {
  if (!isWorker(req)) return NextResponse.json({ detail: "bad worker token" }, { status: 401 });
  await initDb();
  const rows = await q(`SELECT * FROM jobs ORDER BY created_at ASC`);
  const today = new Date().toISOString().slice(0, 10);
  const pending: any[] = [];
  let uploadedToday = 0;
  for (const r of rows) {
    let clips: any[] = [];
    try { clips = JSON.parse(r.clips || "[]"); } catch { clips = []; }
    for (const c of clips) {
      if (c.upload_status === "pending") {
        pending.push({ job_id: r.id, job_title: r.title, clip: c, job_clips: clips });
      }
      if (c.uploaded_at &&
          new Date(c.uploaded_at * 1000).toISOString().slice(0, 10) === today) {
        uploadedToday++;
      }
    }
  }
  return NextResponse.json({ pending, uploaded_today: uploadedToday });
}
