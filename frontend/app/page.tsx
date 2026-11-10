"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, uploadVideo } from "../services/api";

export default function Home() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [projects, setProjects] = useState<any[]>([]);
  const [health, setHealth] = useState<any>(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () => api.projects().then(setProjects).catch(() => {});
  useEffect(() => { load(); api.health().then(setHealth).catch(() => setHealth({ ok: false })); }, []);

  async function startYouTube() {
    setErr(""); setBusy("Creating project…");
    try {
      const p = await api.createYouTube(url.trim());
      localStorage.setItem("currentProject", p.id);
      await api.process(p.id);
      router.push(`/processing?project=${p.id}`);
    } catch (e: any) { setErr(e.message); setBusy(""); }
  }

  async function startUpload(f: File) {
    setErr(""); setBusy(`Uploading ${f.name}…`);
    try {
      const p = await uploadVideo(f, f.name);
      localStorage.setItem("currentProject", p.id);
      await api.process(p.id);
      router.push(`/processing?project=${p.id}`);
    } catch (e: any) { setErr(e.message); setBusy(""); }
  }

  return (
    <div className="space-y-8">
      <section className="rounded-2xl bg-panel p-6">
        <h1 className="text-2xl font-bold">Turn a long video into Shorts — automatically</h1>
        <p className="mt-1 text-sm text-white/60">
          <b>Laya</b> (mmBERT decision model) picks and scores the best moments. <b>Ollama qwen3:4b</b> writes titles,
          hooks & hashtags. Faster-Whisper transcribes. FFmpeg renders true 1080×1920 Shorts. No paid APIs, ever.
        </p>
        {health && (
          <div className="mt-3 flex flex-wrap gap-2 text-xs">
            <span className={`rounded-full px-2 py-1 ${health.ok ? "bg-green-500/20 text-green-300" : "bg-red-500/20 text-red-300"}`}>Backend {health.ok ? "online" : "offline — start it with run.bat"}</span>
            <span className="rounded-full bg-white/5 px-2 py-1">Laya: {health.laya?.installed ? "installed" : "not installed (heuristic fallback active)"}</span>
            <span className="rounded-full bg-white/5 px-2 py-1">Ollama: {health.ollama?.online ? (health.ollama.model_present ? `${health.ollama_model} ready` : `online — run: ollama pull ${health.ollama_model}`) : "offline — start Ollama"}</span>
            {health.usage?.vram_used_mb != null && <span className="rounded-full bg-white/5 px-2 py-1">VRAM {health.usage.vram_used_mb}/{health.usage.vram_total_mb} MB</span>}
          </div>
        )}
        <div className="mt-5 flex gap-2 flex-wrap">
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Paste a YouTube URL…"
            className="min-w-64 flex-1 rounded-xl border border-white/10 bg-black/30 px-4 py-3 outline-none focus:border-accent" />
          <button onClick={startYouTube} disabled={!url || !!busy}
            className="rounded-xl bg-accent px-5 py-3 font-semibold text-black disabled:opacity-40">▶ Start processing</button>
          <button onClick={() => fileRef.current?.click()} disabled={!!busy}
            className="rounded-xl border border-white/20 px-5 py-3 disabled:opacity-40">⬆ Upload MP4 / MOV / MKV</button>
          <input ref={fileRef} type="file" accept=".mp4,.mov,.mkv,.webm,video/*" className="hidden"
            onChange={(e) => e.target.files?.[0] && startUpload(e.target.files[0])} />
        </div>
        {busy && <p className="mt-3 animate-pulse text-sm text-accent">{busy}</p>}
        {err && <p className="mt-3 text-sm text-red-300">{err}</p>}
      </section>

      <section>
        <h2 className="mb-3 font-semibold text-white/80">Recent projects</h2>
        {projects.length === 0 && <p className="text-sm text-white/40">No projects yet — paste a link above to create your first one.</p>}
        <div className="grid gap-3 md:grid-cols-2">
          {projects.map((p) => (
            <button key={p.id} onClick={() => { localStorage.setItem("currentProject", p.id); router.push(`/analysis?project=${p.id}`); }}
              className="rounded-2xl bg-panel p-4 text-left hover:ring-1 hover:ring-accent/60">
              <div className="font-medium">{p.title}</div>
              <div className="mt-1 text-xs text-white/50">{p.source_type} · {p.status} · {p.language || "auto"} · {new Date(p.created_at).toLocaleString()}</div>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
