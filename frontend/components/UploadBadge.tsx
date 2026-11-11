/** YouTube upload status badge — data worker clip ke metadata.upload
 *  me likhta hai (cloud worker flow se). Manual/local-only clips par
 *  kuch nahi dikhta. */
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
        ✅ YouTube par upload ho gayi{when ? ` · ${when}` : ""}{" "}
        {up.youtube_url && (
          <a className="underline" href={up.youtube_url} target="_blank" rel="noreferrer">
            video dekho ↗
          </a>
        )}
      </div>
    );
  }
  if (up.status === "pending") {
    return (
      <div className="rounded-xl bg-yellow-500/15 px-3 py-2 text-sm text-yellow-200">
        ⏳ YouTube upload scheduled hai — set time par khud upload ho jayegi
        (cloud dashboard me times/limit set hote hain)
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
