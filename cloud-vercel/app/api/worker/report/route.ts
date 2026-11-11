import { NextRequest, NextResponse } from "next/server";
import { isWorker } from "@/lib/auth";
import { initDb, q } from "@/lib/db";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!isWorker(req)) return NextResponse.json({ detail: "bad worker token" }, { status: 401 });
  await initDb();
  const body = await req.json().catch(() => ({}));
  const jid = String(body.job_id || "");
  if (!jid) return NextResponse.json({ detail: "job_id required" }, { status: 400 });
  const fields: Record<string, any> = { updated_at: Date.now() / 1000 };
  for (const k of ["status", "stage", "message", "title"]) {
    if (k in body) fields[k] = String(body[k]).slice(0, 500);
  }
  if ("clips" in body) fields.clips = JSON.stringify(body.clips).slice(0, 20000);
  const keys = Object.keys(fields);
  const setClause = keys.map((k, i) => `${k}=$${i + 1}`).join(", ");
  await q(`UPDATE jobs SET ${setClause} WHERE id=$${keys.length + 1}`,
    [...keys.map((k) => fields[k]), jid]);
  return NextResponse.json({ ok: true });
}
