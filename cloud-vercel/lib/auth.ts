/**
 * Single-password auth — deliberately identical to cloud/app.py so the
 * existing laptop worker (worker.py) works unchanged against this API:
 *
 *   SECRET_HEX    = sha256hex("hsg-cloud:" + password)
 *   session token = HMAC_SHA256(SECRET_HEX, "session")
 *   worker token  = env WORKER_TOKEN or HMAC_SHA256(SECRET_HEX, "worker")
 */
import { createHash, createHmac, timingSafeEqual } from "crypto";
import type { NextRequest } from "next/server";

export const PASSWORD = process.env.DASHBOARD_PASSWORD || "shorts123";

const SECRET_HEX = createHash("sha256").update("hsg-cloud:" + PASSWORD).digest("hex");

export const SESSION_TOKEN = createHmac("sha256", SECRET_HEX)
  .update("session")
  .digest("hex");

export const WORKER_TOKEN =
  process.env.WORKER_TOKEN ||
  createHmac("sha256", SECRET_HEX).update("worker").digest("hex");

function safeEq(a: string, b: string): boolean {
  const ba = Buffer.from(a);
  const bb = Buffer.from(b);
  return ba.length === bb.length && timingSafeEqual(ba, bb);
}

export function passwordOk(pw: string): boolean {
  return safeEq(pw, PASSWORD);
}

export function isAuthed(req: NextRequest): boolean {
  const c = req.cookies.get("hsg_session")?.value || "";
  return safeEq(c, SESSION_TOKEN);
}

export function isWorker(req: NextRequest): boolean {
  const t = req.headers.get("x-worker-token") || "";
  return safeEq(t, WORKER_TOKEN) || isAuthed(req);
}
