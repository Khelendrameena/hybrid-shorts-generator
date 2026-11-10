"use client";
import { useState, Suspense } from "react";
import { api, fmtTime } from "../../services/api";
import { useProject } from "../../hooks/useProject";

function EditorInner() {
  const { pid, project } = useProject();
  const [msg, setMsg] = useState("");
  if (!pid) return <p className="text-white/50">No project selected.</p>;
  const clips = project?.clips || [];

  async function patch(cid: string, patch: any, note: string) {
    await api.patchClip(cid, patch);
    setMsg(note);
    setTimeout(() => location.reload(), 500);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className="text-xl font-bold">Shorts Editor</h1>
        <button onClick={async () => { await api.render(pid); setMsg("Rendering approved clips — watch progress in Processing."); }}
          className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-black">🎬 Render approved clips</button>
        {msg && <span className="text-sm text-accent">{msg}</span>}
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
