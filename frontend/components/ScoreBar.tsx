export default function ScoreBar({ label, value }: { label: string; value: number }) {
  const v = Math.max(0, Math.min(100, Math.round(value || 0)));
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-36 text-white/60">{label}</span>
      <div className="h-2 flex-1 rounded bg-white/10 overflow-hidden">
        <div className="h-full bg-accent" style={{ width: `${v}%` }} />
      </div>
      <span className="w-8 text-right font-mono">{v}</span>
    </div>
  );
}
