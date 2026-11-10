// API client for the FastAPI backend (default http://localhost:8000).
export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function req(path: string, opts: RequestInit = {}) {
  const r = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try { const j = await r.json(); msg = j.detail || msg; } catch {}
    throw new Error(msg);
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("application/json") ? r.json() : r.text();
}

export const api = {
  health: () => req("/api/health"),
  settings: () => req("/api/settings"),
  saveSettings: (s: any) => req("/api/settings", { method: "POST", body: JSON.stringify(s) }),
  projects: () => req("/api/projects"),
  project: (id: string) => req(`/api/projects/${id}`),
  createYouTube: (url: string, title?: string) =>
    req("/api/projects/youtube", { method: "POST", body: JSON.stringify({ url, title }) }),
  process: (id: string, opts: any = {}) =>
    req(`/api/projects/${id}/process`, { method: "POST", body: JSON.stringify(opts) }),
  resume: (id: string) => req(`/api/projects/${id}/resume`, { method: "POST" }),
  render: (id: string) => req(`/api/projects/${id}/render`, { method: "POST" }),
  job: (id: string) => req(`/api/jobs/${id}`),
  cancel: (id: string) => req(`/api/jobs/${id}/cancel`, { method: "POST" }),
  transcript: (id: string) => req(`/api/projects/${id}/transcript`),
  analysis: (id: string) => req(`/api/projects/${id}/analysis`),
  patchClip: (cid: string, patch: any) =>
    req(`/api/clips/${cid}`, { method: "PATCH", body: JSON.stringify(patch) }),
  regenerate: (cid: string) => req(`/api/clips/${cid}/regenerate`, { method: "POST" }),
  downloadUrl: (pid: string, cid: string) => `${API}/api/projects/${pid}/clips/${cid}/download`,
  exportUrl: (pid: string) => `${API}/api/projects/${pid}/export.zip`,
  srtUrl: (pid: string) => `${API}/api/projects/${pid}/transcript.srt`,
};

export async function uploadVideo(file: File, title: string) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("title", title);
  const r = await fetch(`${API}/api/projects/upload`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(`Upload failed: HTTP ${r.status}`);
  return r.json();
}

export function fmtTime(sec: number) {
  if (!isFinite(sec)) return "0:00";
  const m = Math.floor(sec / 60), s = Math.floor(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
