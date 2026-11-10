const STAGES = [
  ["downloading", "Download"], ["probing", "Metadata"], ["transcribing", "Whisper"],
  ["analysing_video", "Video analysis"], ["laya_analysis", "Laya decisions"],
  ["ollama_generation", "Ollama creative"], ["rendering", "Rendering"],
];

export default function ProgressStages({ job }: { job: any }) {
  if (!job) return <p className="text-white/50 text-sm">No job running for this project yet.</p>;
  const idx = STAGES.findIndex(([s]) => s === job.stage);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {STAGES.map(([s, label], i) => (
          <span key={s} className={`rounded-full px-3 py-1 text-xs ${
            job.stage === "done" || i < idx ? "bg-green-500/20 text-green-300"
            : i === idx ? "bg-accent text-black font-semibold"
            : "bg-white/5 text-white/40"}`}>{label}</span>
        ))}
        {["failed", "cancelled"].includes(job.stage) && (
          <span className="rounded-full px-3 py-1 text-xs bg-red-500/20 text-red-300">{job.stage}</span>)}
      </div>
      <div className="h-3 rounded bg-white/10 overflow-hidden">
        <div className="h-full bg-accent transition-all" style={{ width: `${job.progress || 0}%` }} />
      </div>
      <p className="text-sm text-white/70">{job.message || job.stage} {job.error ? `— ${job.error}` : ""}</p>
    </div>
  );
}
