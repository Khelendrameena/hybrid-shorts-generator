"use client";
import { useEffect, useState, Suspense } from "react";
import { api, fmtTime } from "../../services/api";
import { useProject } from "../../hooks/useProject";
import ScoreBar from "../../components/ScoreBar";

const LABELS: Record<string, string> = {
  hook_strength: "Hook strength", emotional_intensity: "Emotional intensity",
  information_value: "Information value", standalone_context: "Standalone context",
  story_completeness: "Story completeness", speech_clarity: "Speech clarity",
  visual_suitability: "Visual suitability",
};

function AnalysisInner() {
  const { pid, project } = useProject();
  const [transcript, setTranscript] = useState<any>(null);
  useEffect(() => { if (pid) api.transcript(pid).then(setTranscript).catch(() => {}); }, [pid]);
  if (!pid) return <p className="text-white/50">No project selected.</p>;
  const clips = project?.clips || [];
  const duration = project?.duration || 1;
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">AI Analysis {project ? `— ${project.title}` : ""}</h1>

      <section className="rounded-2xl bg-panel p-5">
        <h2 className="mb-2 text-sm font-semibold text-white/70">Timeline of detected highlights</h2>
        <div className="relative h-10 rounded bg-white/5">
          {clips.map((c: any) => (
            <div key={c.id} title={`${c.display_id || c.id} · score ${c.score}`}
              className="absolute top-1 h-8 rounded bg-accent/80"
              style={{ left: `${(c.start / duration) * 100}%`, width: `${Math.max(1.5, ((c.end - c.start) / duration) * 100)}%` }} />
          ))}
        </div>
        <div className="mt-1 flex justify-between text-xs text-white/40"><span>0:00</span><span>{fmtTime(duration)}</span></div>
      </section>

      <section className="grid gap-3">
        {clips.length === 0 && <p className="text-sm text-white/40">No clips yet — processing may still be running.</p>}
        {clips.map((c: any) => (
          <div key={c.id} className="rounded-2xl bg-panel p-5">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="rounded bg-accent px-2 py-0.5 font-mono text-sm font-bold text-black">{Math.round(c.score)}</span>
              <b>{c.display_id || c.id}</b>
              <span className="text-sm text-white/60">{fmtTime(c.start)} → {fmtTime(c.end)} ({Math.round(c.end - c.start)}s)</span>
              <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs">{c.category}</span>
              <span className="rounded-full bg-white/5 px-2 py-0.5 text-xs">engine: {c.engine || "laya"}</span>
              <span className="ml-auto text-xs text-white/40">{c.status}</span>
            </div>
            <div className="mt-3 grid gap-1 md:grid-cols-2">
              {Object.entries(LABELS).map(([k, label]) => <ScoreBar key={k} label={label} value={c.scores?.[k] ?? 0} />)}
            </div>
            <p className="mt-3 text-sm text-white/70">“{c.transcript}”</p>
            <p className="mt-2 text-xs text-white/40">{(c.reasons || []).join(" · ")}</p>
          </div>
        ))}
      </section>

      <section className="rounded-2xl bg-panel p-5">
        <h2 className="mb-2 text-sm font-semibold text-white/70">Full transcript {transcript ? `(${transcript.language}, ${transcript.segments?.length} segments)` : ""}</h2>
        <div className="max-h-96 space-y-1 overflow-auto text-sm">
          {(transcript?.segments || []).map((s: any) => (
            <p key={s.id}><span className="mr-2 font-mono text-xs text-accent">{fmtTime(s.start)}</span>{s.text}</p>
          ))}
          {!transcript && <p className="text-white/40">Transcript not available yet.</p>}
        </div>
      </section>
    </div>
  );
}

export default function Analysis() {
  return (<Suspense fallback={<p className="text-white/50">Loading…</p>}><AnalysisInner /></Suspense>);
}
