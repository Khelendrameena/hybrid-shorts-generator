"use client";
import { useEffect, useRef, useState, Suspense } from "react";
import { api, fmtTime } from "../../services/api";
import { useProject } from "../../hooks/useProject";
import UploadBadge from "../../components/UploadBadge";

function EditorInner() {
  const { pid, project } = useProject();
  const [msg, setMsg] = useState("");
  const [rendering, setRendering] = useState(false);
  const [renderErr, setRenderErr] = useState("");
  const pollRef = useRef<any>(null);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  if (!pid) return <p className="text-white/50">No project selected.</p>;
  const clips = project?.clips || [];

  async function patch(cid: string, patch: any, note: string) {
    await api.patchClip(cid, patch);
    setMsg(note);
    setTimeout(() => location.reload(), 500);
  }

  const approvedCount = clips.filter((c: any) => c.status === "approved" || c.status === "rendered").length;

  async function startRender() {
    if (!pid || rendering) return;
    if (approvedCount === 0) {
      setRenderErr("Pehle kam se kam ek clip ko ✓ Approve karo — abhi koi approved clip nahi hai, isliye render karne ke liye kuch hai hi nahi.");
      return;
    }
    setRenderErr("");
    setRendering(true);
    setMsg("Rendering started…");
    try {
      await api.render(pid);
    } catch (e: any) {
      setRendering(false);
      setRenderErr(String(e?.message || e));
      return;
    }
    const t0 = Date.now();
    pollRef.current = setInterval(async () => {
      try {
        const p = await api.project(pid);
        const job = p?.job;
        if (job?.stage === "rendering") {
          setMsg(`🎬 Rendering… ${Math.round(job.progress || 0)}% — ${job.message || ""}`);
        } else if (job?.stage === "done") {
          clearInterval(pollRef.current);
          setRendering(false);
          setMsg("✅ Rendering complete — download links are on each clip.");
          setTimeout(() => location.reload(), 900);
        } else if (job?.stage === "failed" || job?.stage === "cancelled") {
          clearInterval(pollRef.current);
          setRendering(false);
          setRenderErr(job.error || `Render ${job.stage} — check the backend terminal for the FFmpeg error.`);
        }
      } catch {}
      if (Date.now() - t0 > 15 * 60 * 1000) {
        clearInterval(pollRef.current);
        setRendering(false);
        setMsg("Rendering is taking long — check the Processing page or backend terminal.");
      }
    }, 3000);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-xl font-bold">Shorts Editor</h1>
        <button onClick={startRender} disabled={rendering}
          className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-black disabled:opacity-50">🎬 Render approved clips ({approvedCount})</button>
        {msg && <span className="text-sm text-accent">{msg}</span>}
        {renderErr && <span className="text-sm text-red-400">⚠ {renderErr}</span>}
      </div>
      <p className="text-xs text-white/40">Timestamps and scores come from Laya and are shown for review — editing a title never changes them. Change start/end here if you want a different cut, then Approve.</p>
      {clips.length === 0 && <p className="text-sm text-white/40">No clips yet.</p>}
      <div className="grid gap-4 lg:grid-cols-2">
        {clips.map((c: any) => (
          <ClipCard key={c.id} clip={c} pid={pid} onPatch={patch} />
        ))}
      </div>
    </div>
  );
}

function ClipCard({ clip: c, pid, onPatch }: any) {
  const [start, setStart] = useState(c.start);
  const [end, setEnd] = useState(c.end);
  const [title, setTitle] = useState(c.metadata?.title || "");
  const [hook, setHook] = useState(c.metadata?.opening_hook || "");
  return (
    <div className="rounded-2xl bg-panel p-5 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="rounded bg-accent px-2 py-0.5 font-mono text-sm font-bold text-black">{Math.round(c.score)}</span>
        <b>{c.display_id || c.id}</b><span className="text-xs text-white/50">{c.category} · {c.status}</span>
        {c.output_path && <a className="ml-auto text-sm text-accent underline" href={api.downloadUrl(pid, c.id)}>⬇ Download MP4</a>}
      </div>
      <div className="flex items-center gap-2 text-sm">
        <label>Start <input type="number" step="0.1" value={start} onChange={(e) => setStart(parseFloat(e.target.value))}
          className="w-20 rounded bg-black/30 px-2 py-1" /></label>
        <label>End <input type="number" step="0.1" value={end} onChange={(e) => setEnd(parseFloat(e.target.value))}
          className="w-20 rounded bg-black/30 px-2 py-1" /></label>
        <span className="text-white/50">{fmtTime(start)} → {fmtTime(end)}</span>
        <button onClick={() => onPatch(c.id, { start, end }, "Timestamps updated")} className="rounded bg-white/10 px-3 py-1">Save cut</button>
      </div>
      {c.output_path && (
        <div className="flex items-start gap-3">
          <video controls preload="metadata" src={api.downloadUrl(pid, c.id)}
            className="w-40 aspect-[9/16] rounded-xl bg-black" />
          <p className="text-xs text-white/50">✅ Rendered Short — yahi play karke dekho, ya upar ⬇ Download MP4 se file lo.
            Saari rendered Shorts ek saath chahiye to Export page se ZIP download karo.</p>
        </div>
      )}
      <UploadBadge c={c} />
      <p className="text-sm text-white/70 line-clamp-3">“{c.transcript}”</p>
      <label className="block text-xs text-white/50">Title
        <input value={title} onChange={(e) => setTitle(e.target.value)} className="mt-1 w-full rounded bg-black/30 px-3 py-2 text-sm text-white" /></label>
      <label className="block text-xs text-white/50">Opening hook
        <input value={hook} onChange={(e) => setHook(e.target.value)} className="mt-1 w-full rounded bg-black/30 px-3 py-2 text-sm text-white" /></label>
      <div className="text-xs text-white/50">
        {(c.metadata?.hashtags || []).join(" ")} · thumb: “{c.metadata?.thumbnail_text || ""}” · {c.metadata?.language || ""} · captions: {c.metadata?.caption_style || ""}
        {c.metadata?.source && <> · via {c.metadata.source}</>}
      </div>
      {(c.metadata?.alternative_titles || []).length > 0 && (
        <div className="flex flex-wrap gap-1">{c.metadata.alternative_titles.map((t: string, i: number) => (
          <button key={i} onClick={() => setTitle(t)} className="rounded-full bg-white/5 px-2 py-0.5 text-xs hover:bg-white/10">{t}</button>))}
        </div>)}
      <div className="flex gap-2 flex-wrap">
        <button onClick={() => onPatch(c.id, { metadata: { ...c.metadata, title, opening_hook: hook } }, "Metadata saved")}
          className="rounded-xl bg-white/10 px-3 py-2 text-sm">Save metadata</button>
        <button onClick={async () => { const md = await api.regenerate(c.id); setTitle(md.title); setHook(md.opening_hook); }}
          className="rounded-xl bg-white/10 px-3 py-2 text-sm">↻ Regenerate (Ollama)</button>
        <button onClick={() => onPatch(c.id, { status: "approved" }, "Approved ✓")}
          className="rounded-xl bg-green-500 px-3 py-2 text-sm font-semibold text-black">✓ Approve</button>
        <button onClick={() => onPatch(c.id, { status: "rejected" }, "Rejected")}
          className="rounded-xl bg-red-500/80 px-3 py-2 text-sm font-semibold">✕ Reject</button>
      </div>
    </div>
  );
}

export default function Editor() {
  return (<Suspense fallback={<p className="text-white/50">Loading…</p>}><EditorInner /></Suspense>);
}
