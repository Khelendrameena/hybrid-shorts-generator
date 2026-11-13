/** YouTube upload status badge — status clip ke metadata.upload me
 *  backend likhta hai (background upload thread, asal progress % ke
 *  saath). Kabhi upload start hi nahi hua to kuch nahi dikhta. */
export default function UploadBadge({ c }: { c: any }) {
  const up = c?.metadata?.upload;
  if (!up || !up.status || up.status === "none") return null;

  if (up.status === "uploaded") {
    const when = up.uploaded_at
      ? new Date(up.uploaded_at * 1000).toLocaleString("en-IN", {
          day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
        })
      : "";
    return (
      <div className="rounded-xl bg-green-500/15 px-3 py-2 text-sm text-green-300">
        ✅ YouTube par upload ho gayi{when ? ` · ${when}` : ""}{up.thumbnail === "set" ? " · 🖼 thumbnail laga hai" : ""}{" "}
        {up.youtube_url && (
          <a className="underline" href={up.youtube_url} target="_blank" rel="noreferrer">
            video dekho ↗
          </a>
        )}
      </div>
    );
  }
  if (up.status === "uploading") {
    const pct = Math.max(0, Math.min(100, Math.round(up.progress || 0)));
    return (
      <div className="rounded-xl bg-blue-500/15 px-3 py-2 text-sm text-blue-200 space-y-1.5">
        <div>⬆ YouTube par upload ho raha hai… {pct}%</div>
        <div className="h-1.5 rounded bg-white/10 overflow-hidden">
          <div className="h-full bg-blue-400 transition-all duration-500" style={{ width: `${pct}%` }} />
        </div>
      </div>
    );
  }
  if (up.status === "failed") {
    return (
      <div className="rounded-xl bg-red-500/15 px-3 py-2 text-sm text-red-300">
        ⚠ YouTube upload fail hua{up.error ? `: ${up.error}` : ""} — Editor me
        ⬆ Upload button se dobara try karo
      </div>
    );
  }
  if (up.status === "pending") {
    return (
      <div className="rounded-xl bg-yellow-500/15 px-3 py-2 text-sm text-yellow-200">
        ⏳ Ye clip abhi YouTube par nahi gayi hai — Editor me iske
        ⬆ Upload button se manually bhej do
      </div>
    );
  }
  if (up.status === "missing") {
    return (
      <div className="rounded-xl bg-red-500/15 px-3 py-2 text-sm text-red-300">
        ⚠️ Upload ke time par render file laptop par nahi mili — cloud dashboard dekho
      </div>
    );
  }
  return null;
}
