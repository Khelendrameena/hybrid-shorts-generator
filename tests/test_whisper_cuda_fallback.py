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


def test_pip_nvidia_lib_dirs_discovery(tmp_path, monkeypatch):
    """_pip_nvidia_lib_dirs() must find <pkg>/lib for nvidia.cublas /
    nvidia.cudnn when the pip CUDA packages are installed."""
    import importlib.util
    from types import SimpleNamespace as NS

    made = {}
    for mod, sub in (("nvidia.cublas", "cublas"), ("nvidia.cudnn", "cudnn")):
        pkg = tmp_path / "nvidia" / sub
        (pkg / "lib").mkdir(parents=True)
        init = pkg / "__init__.py"
        init.write_text("")
        made[mod] = NS(origin=str(init))

    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name: made.get(name))
    dirs = whisper_engine._pip_nvidia_lib_dirs()
    assert dirs == [tmp_path / "nvidia" / "cublas" / "lib",
                    tmp_path / "nvidia" / "cudnn" / "lib"]


def test_preload_pip_cuda_libs_loads_all_three(tmp_path, monkeypatch):
    """Copies of a real .so renamed to the CUDA lib names must load (in
    order) from the pip lib dirs — this is the WSL no-toolkit path."""
    import glob as globmod

    real = next((p for p in globmod.glob("/lib/x86_64-linux-gnu/libm.so.6")
                 + globmod.glob("/usr/lib/x86_64-linux-gnu/libm.so.6")), None)
    if real is None:
        pytest.skip("no system libm to stand in for CUDA libs")
    libdir = tmp_path / "lib"
    libdir.mkdir()
    for name in ("libcublasLt.so.12", "libcublas.so.12", "libcudnn.so.9"):
        shutil.copy(real, libdir / name)
    monkeypatch.setattr(whisper_engine, "_pip_nvidia_lib_dirs", lambda: [libdir])
    whisper_engine._LOADED_HANDLES.clear()
    assert whisper_engine._preload_pip_cuda_libs() is True
    # missing one lib -> honest False
    (libdir / "libcudnn.so.9").unlink()
    whisper_engine._LOADED_HANDLES.clear()
    assert whisper_engine._preload_pip_cuda_libs() is False


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
