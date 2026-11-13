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
  const [uploading, setUploading] = useState(false);
  const [upSecs, setUpSecs] = useState(0);
  const [upErr, setUpErr] = useState("");
  const [doneUrl, setDoneUrl] = useState("");
  const [thumbInfo, setThumbInfo] = useState("");
  const [thumbBusy, setThumbBusy] = useState(false);
  const [thumbMsg, setThumbMsg] = useState("");
  const [upPct, setUpPct] = useState(0);
  const watchRef = useRef<any>(null);
  const alreadyUp = c.metadata?.upload?.status === "uploaded";

  // Upload ab backend me background chalta hai aur asal progress %
  // clip ke metadata.upload me aati hai — yahan poll karke wahi %
  // button par dikhate hain. Page refresh ke baad bhi (neeche wala
  // effect) watching apne aap resume ho jati hai, kyunki status DB
  // me hai, browser ke ghumte spinner me nahi.
  function stopWatch() {
    if (watchRef.current) { clearInterval(watchRef.current); watchRef.current = null; }
  }

  function watchUpload() {
    if (watchRef.current) return;
    const t0 = Date.now();
    watchRef.current = setInterval(async () => {
      try {
        const p = await api.project(pid);
        const me = (p?.clips || []).find((x: any) => x.id === c.id);
        const u = me?.metadata?.upload;
        if (u?.status === "uploading") {
          setUpPct(u.progress || 0);
        } else if (u?.status === "uploaded") {
          stopWatch();
          setUploading(false);
          setDoneUrl(u.youtube_url || "");
          setThumbInfo(u.thumbnail === "set"
            ? " · 🖼 thumbnail bhi apne aap lag gaya"
            : u.thumbnail_error ? ` · ⚠ thumbnail nahi laga (${u.thumbnail_error})` : "");
          setTimeout(() => location.reload(), 1200);
        } else if (u?.status === "failed") {
          stopWatch();
          setUploading(false);
          setUpErr(u.error || "YouTube upload fail hua — dobara try karo");
        }
      } catch {}
      if (Date.now() - t0 > 20 * 60 * 1000) {
        stopWatch();
        setUploading(false);
        setUpErr("Upload 20 minute se zyada atka hai — backend wala terminal dekho, phir dobara try karo");
      }
    }, 3000);
  }

  useEffect(() => {
    if (c.metadata?.upload?.status === "uploading") {
      setUploading(true);
      setUpPct(c.metadata.upload.progress || 0);
      watchUpload();
    }
    return stopWatch;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Upload chalte hue elapsed seconds dikhao — YouTube upload me
  // 1-3 min lag sakta hai, spinner akela "stuck" lagta hai.
  useEffect(() => {
    if (!uploading) return;
    setUpSecs(0);
    const t = setInterval(() => setUpSecs((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [uploading]);

  function noteThumb(r: any) {
    if (r?.thumbnail === "set") return " · 🖼 thumbnail bhi apne aap lag gaya";
    if (r?.thumbnail === "failed")
      return ` · ⚠ thumbnail nahi laga (${r.thumbnail_error || "channel par custom thumbnail allowed nahi hoga"})`;
    return "";
  }

  async function doUpload() {
    setUploading(true);
    setUpErr("");
    setUpPct(0);
    try {
      // Pehle screen par dikh raha title/hook save karo, taaki upload
      // usi title se jaye jo user dekh raha hai.
      // !!! onPatch() yahan use MAT karo: wo save ke 500ms baad
      // location.reload() karta hai, jo chal rahi upload fetch ko
      // abort kar deta hai — button hamesha "Upload ho raha hai…"
      // par atka dikhta hai aur upload ka jawab kabhi nahi milta
      // (bug report 2026-11-13). Seedha patchClip call karo, reload nahi.
      try {
        await api.patchClip(c.id, { metadata: { ...c.metadata, title, opening_hook: hook } });
      } catch {}
      const r = await api.uploadClip(c.id);
      if (r?.status === "uploading") {
        // Asal upload backend me background chal raha hai aur ye
        // request turant wapas aa gayi hai — asal progress % poll
        // karke dikhayenge (watchUpload); uploading state wahi band
        // karega, isliye yahan setUploading(false) nahi karte.
        watchUpload();
        return;
      }
      setDoneUrl(r.youtube_url || "");
      setThumbInfo(noteThumb(r));
      setUploading(false);
    } catch (e: any) {
      setUpErr(String(e?.message || e));
      setUploading(false);
    }
  }

  async function doThumbnail() {
    setThumbBusy(true);
    setThumbMsg("");
    try {
      const r = await api.uploadClip(c.id);
      setThumbMsg(r?.thumbnail === "set"
        ? "🖼 Thumbnail lag gaya ✓ (page refresh par badge me bhi dikhega)"
        : `⚠ Thumbnail nahi laga: ${r?.thumbnail_error || "unknown error"}`);
    } catch (e: any) {
      setThumbMsg(`⚠ ${String(e?.message || e)}`);
    } finally {
      setThumbBusy(false);
    }
  }
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
      {alreadyUp && c.metadata?.upload?.thumbnail !== "set" && (
        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={doThumbnail} disabled={thumbBusy}
            className="rounded-xl bg-white/10 px-3 py-2 text-sm disabled:opacity-50">
            {thumbBusy ? "⏳ Thumbnail lag raha hai…" : "🖼 Thumbnail lagao (auto)"}
          </button>
          {thumbMsg && <span className="text-xs text-white/60">{thumbMsg}</span>}
        </div>
      )}
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
        {c.output_path && !alreadyUp && !doneUrl && (
          <button onClick={doUpload} disabled={uploading}
            className="rounded-xl bg-red-600 px-3 py-2 text-sm font-semibold disabled:opacity-50">
            {uploading ? `⏳ Upload ho raha hai… ${upPct}% · ${upSecs}s` : "⬆ YouTube par upload karo"}
          </button>
        )}
      </div>
      {doneUrl && (
        <p className="text-sm text-green-300">✅ Upload ho gaya (Public) —{" "}
          <a className="underline" href={doneUrl} target="_blank" rel="noreferrer">video dekho ↗</a>
          {thumbInfo}
          {" "}(page refresh par neeche badge bhi update ho jayega)</p>
      )}
      {upErr && <p className="text-sm text-red-400">⚠ Upload nahi hua: {upErr}</p>}
    </div>
  );
}

export default function Editor() {
  return (<Suspense fallback={<p className="text-white/50">Loading…</p>}><EditorInner /></Suspense>);
}
