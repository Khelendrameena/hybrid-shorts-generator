import { NextRequest, NextResponse } from "next/server";
import { SESSION_TOKEN, passwordOk } from "@/lib/auth";
export const dynamic = "force-dynamic";

const page = (error: string) => `<!doctype html><meta charset="utf-8"><title>Shorts Cloud — Login</title>
<body style="background:#0b0e14;color:#e6e6e6;font-family:system-ui;display:flex;
align-items:center;justify-content:center;height:100vh;margin:0">
<form method="post" action="/login" style="background:#141926;padding:28px;border-radius:14px;width:300px">
<h2 style="margin:0 0 6px">🎬 Shorts Cloud</h2>
<p style="color:#8b93a7;font-size:13px;margin:0 0 16px">Sirf tumhare liye — password daalo</p>
<input type="password" name="password" placeholder="Password" autofocus
 style="width:100%;padding:10px;border-radius:8px;border:1px solid #2a3247;background:#0b0e14;color:#fff;box-sizing:border-box">
<button style="width:100%;margin-top:12px;padding:10px;border:0;border-radius:8px;
background:#e5484d;color:#fff;font-weight:600;cursor:pointer">Login</button>
<p style="color:#e5484d;font-size:12px">${error}</p></form></body>`;

export async function GET() {
  return new NextResponse(page(""), { headers: { "Content-Type": "text/html" } });
}

export async function POST(req: NextRequest) {
  const form = await req.formData();
  if (passwordOk(String(form.get("password") || ""))) {
    const res = NextResponse.redirect(new URL("/", req.url), 303);
    res.cookies.set("hsg_session", SESSION_TOKEN, {
      httpOnly: true, sameSite: "lax", path: "/", maxAge: 60 * 60 * 24 * 30,
    });
    return res;
  }
  return new NextResponse(page("Galat password — phir try karo"), {
    status: 401, headers: { "Content-Type": "text/html" },
  });
}
