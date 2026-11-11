import { NextRequest, NextResponse } from "next/server";
import { randomBytes } from "crypto";
import { isAuthed } from "@/lib/auth";
import { initDb, q } from "@/lib/db";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  if (!isAuthed(req)) return NextResponse.json({ detail: "login required" }, { status: 401 });
  await initDb();
  const body = await req.json();
  const url = String(body.url || "").trim();
  if (!url) return NextResponse.json({ detail: "url required" }, { status: 400 });
  const id = randomBytes(6).toString("hex");
  const now = Date.now() / 1000;
  await q(
    `INSERT INTO jobs (id, kind, source_url, title, status, stage, message,
       clips, auto_upload, created_at, updated_at, claimed_by, video_id)
     VALUES ($1, 'manual', $2, '', 'queued', 'waiting', '', '[]', $3, $4, $4, NULL, '')`,
    [id, url, body.auto_upload ? 1 : 0, now],
  );
  return NextResponse.json({ ok: true, id });
}
