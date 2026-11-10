"use client";
import { Suspense } from "react";
import Link from "next/link";
import { api } from "../../services/api";
import { useProject } from "../../hooks/useProject";
import ProgressStages from "../../components/ProgressStages";

function ProcessingInner() {
  const { pid, project, error } = useProject(2500);
  if (!pid) return <p className="text-white/50">No project selected — start one from Home.</p>;
  const job = project?.job;
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold">Processing {project ? `— ${project.title}` : ""}</h1>
      {error && <p className="text-red-300 text-sm">{error} (is the backend running?)</p>}
      <div className="rounded-2xl bg-panel p-6"><ProgressStages job={job} /></div>
      <div className="flex gap-2 flex-wrap">
        {job && !["done", "failed", "cancelled"].includes(job.stage) && (
          <button onClick={() => api.cancel(job.id)} className="rounded-xl border border-red-400/50 px-4 py-2 text-sm text-red-300">Cancel job</button>)}
        {job && ["failed", "cancelled"].includes(job.stage) && (
          <button onClick={() => api.resume(pid)} className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-black">↻ Resume (skips finished stages)</button>)}
        {job?.stage === "done" && (
          <Link href={`/editor?project=${pid}`} className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-black">Open Shorts Editor →</Link>)}
      </div>
      <p className="text-xs text-white/40">Stages run one heavy model at a time (Whisper → Laya → Ollama) so a 4 GB GPU never holds two models together. Progress is saved after every stage — closing this page or restarting the server does not lose work.</p>
    </div>
  );
}

export default function Processing() {
  return (<Suspense fallback={<p className="text-white/50">Loading…</p>}><ProcessingInner /></Suspense>);
}
