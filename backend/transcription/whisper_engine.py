"""Faster-Whisper transcription: multilingual, word + segment timestamps,
automatic language detection (Hindi / English / Hinglish code-switching works
because Whisper is multilingual; language is detected, never forced unless the
user sets one). Original timestamps are preserved exactly and saved as JSON+SRT.

Speaker identification: Faster-Whisper has no built-in diarization. We provide
a lightweight energy/pause-based speaker-turn heuristic ONLY as a hint field
(`speaker_turn` index changes at long pauses) and label it honestly as a
heuristic — it is not true diarization. Plug pyannote later if needed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..config import settings
from ..models.manager import model_manager


def _fmt_srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def segments_to_srt(segments: list[dict]) -> str:
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{_fmt_srt_time(seg['start'])} --> {_fmt_srt_time(seg['end'])}")
        lines.append(seg["text"].strip())
        lines.append("")
    return "\n".join(lines)


class WhisperEngine:
    def __init__(self, model_size: str | None = None, device: str | None = None):
        self.model_size = model_size or settings.whisper_model
        self.device_pref = device or settings.whisper_device
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        from faster_whisper import WhisperModel  # local import: heavy

        device = self.device_pref
        compute = settings.whisper_compute_type
        if device == "auto":
            try:
                import ctranslate2  # type: ignore

                device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                device = "cpu"
        if compute == "default":
            compute = "float16" if device == "cuda" else "int8"
        try:
            self._model = WhisperModel(self.model_size, device=device, compute_type=compute)
            self._device = device
        except Exception:
            # CPU fallback — a GPU failure must never kill the job on a 4GB card.
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
            self._device = "cpu"
        model_manager.register("whisper", self)
        return self._model

    def unload(self):
        self._model = None
        model_manager.release("whisper")

    def transcribe(self, media_path: str | Path, out_dir: str | Path,
                   language: str | None = None, progress_cb=None) -> dict:
        model_manager.acquire("whisper")  # evicts Laya/Ollama from VRAM first
        model = self._load()
        lang = None if (not language or language == "auto") else language
        segments_iter, info = model.transcribe(
            str(media_path), language=lang, beam_size=5,
            word_timestamps=True, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        duration = float(info.duration or 0)
        segments: list[dict] = []
        turn = 0
        prev_end = 0.0
        for seg in segments_iter:
            if seg.start - prev_end > 1.2 and segments:  # long pause → possible turn change (heuristic)
                turn += 1
            words = [
                {"word": w.word, "start": round(float(w.start), 3), "end": round(float(w.end), 3),
                 "probability": round(float(w.probability), 3)}
                for w in (seg.words or [])
            ]
            segments.append({
                "id": len(segments), "start": round(float(seg.start), 3), "end": round(float(seg.end), 3),
                "text": seg.text.strip(), "words": words,
                "avg_logprob": round(float(seg.avg_logprob), 3),
                "no_speech_prob": round(float(seg.no_speech_prob), 3),
                "speaker_turn": turn,  # heuristic hint only — NOT diarization
            })
            prev_end = float(seg.end)
            if progress_cb and duration:
                progress_cb(min(99.0, seg.end / duration * 100.0), f"Transcribing… {int(seg.end)}s / {int(duration)}s")

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        result = {
            "language": info.language, "language_probability": round(float(info.language_probability), 3),
            "duration": duration, "model": self.model_size, "device": getattr(self, "_device", "cpu"),
            "segments": segments,
            "full_text": " ".join(s["text"] for s in segments),
        }
        (out_dir / "transcript.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "transcript.srt").write_text(segments_to_srt(segments), encoding="utf-8")
        if progress_cb:
            progress_cb(100.0, f"Transcription complete ({info.language})")
        self.unload()  # free VRAM for Laya next
        return result


def load_transcript(project_dir_path: str | Path) -> dict | None:
    p = Path(project_dir_path) / "transcript.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))
