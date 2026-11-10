"use client";
import { useEffect, useState } from "react";
import { api } from "../../services/api";

const FIELDS: [string, string, string][] = [
  ["laya_model_id", "Laya model (Hugging Face id / local path)", "text"],
  ["ollama_url", "Ollama server URL", "text"],
  ["ollama_model", "Ollama model", "text"],
  ["whisper_model", "Whisper model (tiny/base/small/medium)", "text"],
  ["max_clips", "Maximum clips", "number"],
  ["min_clip_score", "Minimum clip score (0–100)", "number"],
  ["min_clip_duration", "Minimum clip duration (sec)", "number"],
  ["max_clip_duration", "Maximum clip duration (sec)", "number"],
  ["output_width", "Output width", "number"],
  ["output_height", "Output height", "number"],
];

export default function Settings() {
  const [s, setS] = useState<any>({});
  const [msg, setMsg] = useState("");
  useEffect(() => { api.settings().then(setS).catch(() => {}); }, []);
  const set = (k: string, v: any) => setS((p: any) => ({ ...p, [k]: v }));
  return (
    <div className="space-y-5 max-w-2xl">
      <h1 className="text-xl font-bold">Settings</h1>
      <div className="rounded-2xl bg-panel p-6 space-y-4">
        {FIELDS.map(([k, label, type]) => (
          <label key={k} className="block text-sm text-white/60">{label}
            <input type={type} value={s[k] ?? ""} onChange={(e) => set(k, type === "number" ? parseFloat(e.target.value) : e.target.value)}
              className="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-white outline-none focus:border-accent" />
          </label>
        ))}
        <label className="block text-sm text-white/60">Subtitle theme
          <select value={s.subtitle_theme || "dynamic"} onChange={(e) => set("subtitle_theme", e.target.value)}
            className="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-white">
            <option value="dynamic">Dynamic (word highlight)</option>
            <option value="classic">Classic</option>
            <option value="minimal">Minimal</option>
            <option value="bold-yellow">Bold yellow</option>
          </select></label>
        <label className="block text-sm text-white/60">Transcript source — sabse slow stage yahi hai
          <select value={s.transcript_source || "auto"} onChange={(e) => set("transcript_source", e.target.value)}
            className="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-white">
            <option value="auto">Auto — YouTube ke apne captions pehle (seconds me), na mile to Whisper</option>
            <option value="whisper">Whisper hamesha — local AI transcription (slow but captions na ho tab bhi chalega)</option>
          </select></label>
        <label className="block text-sm text-white/60">Frame mode — Shorts/Reels 9:16 frame me video kaise aaye
          <select value={s.frame_mode || "fit"} onChange={(e) => set("frame_mode", e.target.value)}
            className="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-white">
            <option value="fit">Fit — poora video dikhega, kuch cut nahi hoga (upar-neeche blurred background)</option>
            <option value="crop">Crop — full-screen 9:16 crop (side ka hissa kat sakta hai)</option>
          </select></label>
        <label className="block text-sm text-white/60">Language (auto = detect; hi / en supported, Hinglish handled by Whisper + Laya multilingual)
          <select value={s.default_language || "auto"} onChange={(e) => set("default_language", e.target.value)}
            className="mt-1 w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-white">
            <option value="auto">Auto-detect</option><option value="hi">Hindi</option><option value="en">English</option>
          </select></label>
        <label className="block text-sm text-white/60">Processing device — handled automatically: Whisper/Laya use the GPU when free and fall back to CPU; only one heavy model is loaded at a time on a 4 GB card.</label>
        <button onClick={async () => { await api.saveSettings({
            ollama_model: s.ollama_model, ollama_url: s.ollama_url, laya_model_id: s.laya_model_id,
            whisper_model: s.whisper_model, max_clips: s.max_clips, min_score: s.min_clip_score,
            min_duration: s.min_clip_duration, max_duration: s.max_clip_duration,
            subtitle_theme: s.subtitle_theme, frame_mode: s.frame_mode, transcript_source: s.transcript_source, language: s.default_language,
          }); setMsg("Saved ✓ — applies to the next job."); }}
          className="rounded-xl bg-accent px-5 py-3 font-semibold text-black">Save settings</button>
        {msg && <span className="ml-3 text-sm text-accent">{msg}</span>}
      </div>
      <p className="text-xs text-white/40">Defaults target an RTX 3050 (4 GB VRAM) + 16 GB RAM: Whisper “small”, Laya-multilingual (~0.65 GB fp16), Ollama qwen3:4b (~2.5 GB, unloaded after each generation with keep_alive=0).</p>
    </div>
  );
}
