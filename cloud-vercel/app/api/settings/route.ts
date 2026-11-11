import { NextRequest, NextResponse } from "next/server";
import { isAuthed } from "@/lib/auth";
import { DEFAULT_SETTINGS, initDb, q } from "@/lib/db";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!isAuthed(req)) return NextResponse.json({ detail: "login required" }, { status: 401 });
  await initDb();
  const body = await req.json();
  for (const [k, v] of Object.entries(body)) {
    if (k in DEFAULT_SETTINGS) {
      await q(`INSERT INTO kv (k, v) VALUES ($1, $2)
               ON CONFLICT(k) DO UPDATE SET v=EXCLUDED.v`, [k, String(v)]);
    }
  }
  return NextResponse.json({ ok: true });
}
