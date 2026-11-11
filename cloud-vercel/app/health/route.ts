import { NextResponse } from "next/server";
export const dynamic = "force-dynamic";
export async function GET() {
  return NextResponse.json({ ok: true, service: "hybrid-shorts-cloud", time: Date.now() / 1000 });
}
