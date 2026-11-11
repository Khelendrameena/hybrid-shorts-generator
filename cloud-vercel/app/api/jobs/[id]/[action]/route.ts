import { NextRequest, NextResponse } from "next/server";
import { isAuthed } from "@/lib/auth";
import { initDb, q } from "@/lib/db";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string; action: string }> }) {
  if (!isAuthed(req)) return NextResponse.json({ detail: "login required" }, { status: 401 });
  await initDb();
  const { id, action } = await ctx.params;
  const now = Date.now() / 1000;
  if (action === "cancel") {
    await q(`UPDATE jobs SET status='cancelled', updated_at=$1 WHERE id=$2`, [now, id]);
  } else if (action === "retry") {
    await q(`UPDATE jobs SET status='queued', claimed_by=NULL, stage='waiting',
             message='', updated_at=$1 WHERE id=$2`, [now, id]);
  } else if (action === "delete") {
    await q(`DELETE FROM jobs WHERE id=$1`, [id]);
  } else {
    return NextResponse.json({ detail: "unknown action" }, { status: 404 });
  }
  return NextResponse.json({ ok: true });
}
