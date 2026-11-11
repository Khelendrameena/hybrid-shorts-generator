import { NextRequest, NextResponse } from "next/server";
import { isWorker } from "@/lib/auth";
import { getSettings, initDb, touchWorker } from "@/lib/db";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!isWorker(req)) return NextResponse.json({ detail: "bad worker token" }, { status: 401 });
  await initDb();
  const body = await req.json().catch(() => ({}));
  await touchWorker(String(body.worker_id || "laptop"), String(body.info || ""));
  return NextResponse.json({ ok: true, settings: await getSettings() });
}
