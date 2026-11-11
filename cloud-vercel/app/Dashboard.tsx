"use client";
import { useCallback, useEffect, useRef, useState } from "react";

type Job = {
  id: string; kind: string; source_url: string; title: string;
  status: string; stage: string; message: string;
  clips: { title?: string; youtube_url?: string }[];
};

const CHIP: Record<string, string> = {
  queued: "#3a3f2a|#d7e08a|QUEUED", claimed: "#2a3a5f|#9ec1ff|CLAIMED",
  processing: "#2a3a5f|#9ec1ff|PROCESSING", done: "#23402c|#8ae0a3|DONE",
  failed: "#5f2a2a|#ff9e9e|FAILED", cancelled: "#333|#aaa|CANCELLED",
};

export default function Dashboard() {
  const [state, setState] = useState<any>(null);
  const [form, setForm] = useState<any>(null);
  const [murl, setMurl] = useState("");
  const [mupload, setMupload] = useState(true);
  const [saved, setSaved] = useState("");
  const editing = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch("/api/state");
      if (!r.ok) return;
      const s = await r.json();
      setState(s);
      if (!editing.current) setForm({ ...s.settings });
    } catch { /* retry next tick */ }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  async function saveSettings() {
    await fetch("/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...form, auto_enabled: form.auto_enabled ? "1" : "0" }),
    });
    setSaved("Saved ✓");
    setTimeout(() => setSaved(""), 2000);
    refresh();
  }

  async function addJob() {
    if (!murl.trim()) return alert("URL daalo pehle");
    await fetch("/api/jobs", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: murl.trim(), auto_upload: mupload }),
    });
    setMurl("");
    refresh();
  }

  async function act(id: string, a: string) {
    await fetch(`/api/jobs/${id}/${a}`, { method: "POST" });
    refresh();
  }

  const card: React.CSSProperties = {
    background: "#141926", border: "1px solid #232b3f", borderRadius: 14,
    padding: 16, margin: "14px 0",
  };
  const input: React.CSSProperties = {
    background: "#0b0e14", color: "#fff", border: "1px solid #2a3247",
    borderRadius: 8, padding: 9, width: "100%", boxSizing: "border-box", margin: "4px 0",
  };
  const btn: React.CSSProperties = {
    background: "#e5484d", color: "#fff", border: 0, borderRadius: 8,
    padding: "9px 14px", fontWeight: 600, cursor: "pointer",
  };

  return (
    <div style={{
      background: "#0b0e14", color: "#e6e6e6", fontFamily: "system-ui",
      minHeight: "100vh", padding: 16, maxWidth: 860, margin: "auto",
    }}>
      <h1 style={{ fontSize: 20, margin: "4px 0" }}>
        🎬 Shorts Cloud{" "}
        <small style={{ fontSize: 13 }}>
          {state == null ? "…" : state.worker_online
            ? <><span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: "#3fb950", verticalAlign: "middle" }} /> Laptop worker ONLINE</>
            : <><span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: "#e5484d", verticalAlign: "middle" }} /> Laptop worker offline — jobs queue me safe hain</>}
        </small>
      </h1>
      <small style={{ color: "#8b93a7" }}>
        Phone se control karo — processing tumhare laptop par hoti hai jab wo on ho.
        Laptop off = jobs queue me safe rehte hain.
      </small>

      <div style={card}>
        <h3 style={{ margin: "0 0 10px" }}>🤖 Mode</h3>
        <label>
          <input type="checkbox" checked={!!form?.auto_enabled && form.auto_enabled !== "0"}
            onChange={(e) => setForm({ ...form, auto_enabled: e.target.checked })}
            style={{ transform: "scale(1.5)", marginRight: 10, verticalAlign: "middle" }} />
          <b>AUTO mode</b> — trending long videos khud dhoondhe, clips banaye, YouTube par upload kare
        </label>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 10 }}
          onFocus={() => (editing.current = true)} onBlur={() => (editing.current = false)}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <label style={{ fontSize: 13 }}>Niches (ek line = ek topic)</label>
            <textarea rows={3} style={input} value={form?.niches || ""}
              onChange={(e) => setForm({ ...form, niches: e.target.value })} />
          </div>
          <div style={{ flex: 1, minWidth: 200 }}>
            <label style={{ fontSize: 13 }}>Channels (URLs, ek line = ek — optional)</label>
            <textarea rows={3} style={input} value={form?.channels || ""}
              onChange={(e) => setForm({ ...form, channels: e.target.value })} />
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}
          onFocus={() => (editing.current = true)} onBlur={() => (editing.current = false)}>
          {([
            ["clips_per_video", "Clips per video", "number"],
            ["min_duration", "Min video length (sec)", "number"],
            ["daily_auto_cap", "Auto jobs per day (cap)", "number"],
          ] as const).map(([k, label]) => (
            <div key={k} style={{ flex: 1, minWidth: 130 }}>
              <label style={{ fontSize: 13 }}>{label}</label>
              <input type="number" style={input} value={form?.[k] || ""}
                onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
            </div>
          ))}
          <div style={{ flex: 1, minWidth: 130 }}>
            <label style={{ fontSize: 13 }}>Upload privacy</label>
            <select style={input} value={form?.upload_privacy || "unlisted"}
              onChange={(e) => setForm({ ...form, upload_privacy: e.target.value })}>
              <option value="unlisted">unlisted (pehle check karne ke liye best)</option>
              <option value="public">public</option>
              <option value="private">private</option>
            </select>
          </div>
        </div>
        <button style={btn} onClick={saveSettings}>Settings save karo</button>{" "}
        <small>{saved}</small>
      </div>

      <div style={card}>
        <h3 style={{ margin: "0 0 10px" }}>✋ Manual mode — video add karo</h3>
        <input style={input} placeholder="YouTube video URL paste karo"
          value={murl} onChange={(e) => setMurl(e.target.value)} />
        <label style={{ fontSize: 13 }}>
          <input type="checkbox" checked={mupload}
            onChange={(e) => setMupload(e.target.checked)} />{" "}
          Render ke baad YouTube par upload bhi kar de
        </label>
        <br />
        <button style={{ ...btn, marginTop: 8 }} onClick={addJob}>Queue me daalo</button>{" "}
        <small style={{ color: "#8b93a7" }}>Laptop on hoga to worker ise khud utha lega.</small>
      </div>

      <div style={card}>
        <h3 style={{ margin: "0 0 10px" }}>📋 Queue / Jobs</h3>
        {!state || !state.jobs?.length
          ? <small style={{ color: "#8b93a7" }}>Abhi koi job nahi hai.</small>
          : state.jobs.map((j: Job) => {
            const [bg, fg, label] = (CHIP[j.status] || "#333|#aaa|" + j.status).split("|");
            return (
              <div key={j.id} style={{ borderTop: "1px solid #232b3f", padding: "10px 0" }}>
                <span style={{
                  background: bg, color: fg, padding: "2px 9px", borderRadius: 99,
                  fontSize: 11, fontWeight: 700,
                }}>{label}</span>{" "}
                <b>{j.kind === "auto" ? "🤖 AUTO" : "✋ MANUAL"}</b>{" "}
                <a href={j.source_url} target="_blank" style={{ color: "#9ec1ff" }}>
                  {(j.title || j.source_url).slice(0, 80)}
                </a>
                <br />
                <small style={{ color: "#8b93a7" }}>
                  {j.stage} {j.message ? "— " + j.message : ""}
                </small>
                {(j.clips || []).map((c, i) => (
                  <div key={i}>🎬 {c.title || "clip"}{" "}
                    {c.youtube_url && <>— <a href={c.youtube_url} target="_blank" style={{ color: "#9ec1ff" }}>YouTube par dekho</a></>}
                  </div>
                ))}
                <div style={{ marginTop: 4 }}>
                  {(["retry", "cancel", "delete"] as const).map((a) => (
                    <button key={a} onClick={() => act(j.id, a)} style={{
                      background: "#232b3f", color: "#fff", border: 0, borderRadius: 8,
                      padding: "4px 9px", fontSize: 12, cursor: "pointer", marginRight: 6,
                    }}>{a[0].toUpperCase() + a.slice(1)}</button>
                  ))}
                </div>
              </div>
            );
          })}
      </div>
      <p><a href="/logout" style={{ color: "#9ec1ff" }}>Logout</a></p>
    </div>
  );
}
