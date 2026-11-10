"use client";
import { Suspense } from "react";
import { api, fmtTime } from "../../services/api";
import { useProject } from "../../hooks/useProject";

function ExportPageInner() {
  const { pid, project } = useProject();
  if (!pid) return <p className="text-white/50">No project selected.</p>;
  const clips = project?.clips || [];
  const rendered = clips.filter((c: any) => c.output_path);
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold">Export</h1>
      <div className="rounded-2xl bg-panel p-6 space-y-3">
        <p className="text-sm text-white/60">ZIP contains every rendered Short (1080×1920 MP4), per-clip SRT files, the full transcript (JSON + SRT) and a metadata.json with titles, hooks, hashtags and scores.</p>
        <div className="flex gap-2 flex-wrap">
          <a href={api.exportUrl(pid)} className="rounded-xl bg-accent px-5 py-3 font-semibold text-black">⬇ Download all as ZIP</a>
          <a href={api.srtUrl(pid)} className="rounded-xl border border-white/20 px-5 py-3">⬇ Transcript SRT</a>
        </div>
        <p className="text-xs text-white/40">{rendered.length} of {clips.length} clips rendered. Render approved clips from the Editor first.</p>
      </div>
      <div className="grid gap-3">
        {clips.map((c: any) => (
          <div key={c.id} className="flex items-center gap-3 rounded-2xl bg-panel p-4 flex-wrap">
            <b>{c.display_id || c.id}</b>
            <span className="text-sm text-white/60">{c.metadata?.title || "(no title)"}</span>
            <span className="text-xs text-white/40">{fmtTime(c.start)} → {fmtTime(c.end)} · score {Math.round(c.score)} · {c.status}</span>
            {c.output_path
              ? <a className="ml-auto text-sm text-accent underline" href={api.downloadUrl(pid, c.id)}>⬇ MP4</a>
              : <span className="ml-auto text-xs text-white/30">not rendered</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function ExportPage() {
  return (<Suspense fallback={<p className="text-white/50">Loading…</p>}><ExportPageInner /></Suspense>);
}
