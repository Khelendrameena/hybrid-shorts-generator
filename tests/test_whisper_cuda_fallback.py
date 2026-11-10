"""Regression tests for the libcublas crash (2026-11-10):
under WSL, ctranslate2 reports a CUDA device but libcublas.so.12 is not
installed, so Whisper crashed mid-transcribe instead of using the CPU.
Fixes pinned here: _cuda_usable() probes the library, and transcribe()
retries once on CPU when a CUDA runtime error surfaces during iteration.
"""
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from backend.transcription import whisper_engine
from backend.transcription.whisper_engine import WhisperEngine, _cuda_usable


def test_cuda_usable_returns_bool():
    assert isinstance(_cuda_usable(), bool)


def test_cuda_usable_false_without_cublas(monkeypatch):
    import ctypes

    real_cdll = ctypes.CDLL

    def no_cublas(name, *a, **k):
        if "cublas" in str(name):
            raise OSError("not found")
        return real_cdll(name, *a, **k)

    monkeypatch.setattr(ctypes, "CDLL", no_cublas)
    # Even if a device exists, missing cuBLAS must mean "not usable".
    assert _cuda_usable() is False


class _FakeInfo:
    duration = 2.0
    language = "en"
    language_probability = 0.99


def _fake_seg():
    return SimpleNamespace(
        start=0.0, end=1.0, text=" hello ",
        words=[SimpleNamespace(word=" hello", start=0.0, end=1.0, probability=0.9)],
        avg_logprob=-0.1, no_speech_prob=0.01,
    )


class _FakeModel:
    def __init__(self, device):
        self.device = device

    def transcribe(self, audio, **kwargs):
        if self.device == "cuda":
            def _gen():
                raise RuntimeError("Library libcublas.so.12 is not found or cannot be loaded")
                yield  # pragma: no cover
            return _gen(), _FakeInfo()
        return iter([_fake_seg()]), _FakeInfo()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_transcribe_retries_on_cpu_after_cublas_crash(tmp_path, monkeypatch):
    src = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=2", str(src)],
        check=True,
    )
    engine = WhisperEngine()

    def fake_load(force_cpu=False):
        engine._device = "cpu" if force_cpu else "cuda"
        return _FakeModel(engine._device)

    monkeypatch.setattr(engine, "_load", fake_load)
    monkeypatch.setattr(whisper_engine.model_manager, "acquire", lambda *a, **k: None)
    monkeypatch.setattr(whisper_engine.model_manager, "release", lambda *a, **k: None)

    result = engine.transcribe(src, tmp_path / "out")
    assert result["device"] == "cpu"
    assert result["segments"][0]["text"] == "hello"
    assert (tmp_path / "out" / "transcript.json").exists()
