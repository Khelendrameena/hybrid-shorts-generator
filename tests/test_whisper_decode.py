"""Regression test for the PyAV crash (2026-11-10):
faster-whisper's internal decode called av.open(metadata_errors=...) which
raises TypeError on some PyAV versions. WhisperEngine now decodes audio with
FFmpeg into a numpy array, bypassing PyAV. This test pins that decoder.
"""
import shutil
import subprocess

import numpy as np
import pytest

from backend.transcription.whisper_engine import _decode_audio_ffmpeg

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                reason="ffmpeg not installed")


def test_decode_audio_ffmpeg_returns_16k_mono_float32(tmp_path):
    src = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "sine=frequency=440:duration=2", "-ar", "44100", str(src)],
        check=True,
    )
    audio = _decode_audio_ffmpeg(src)
    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    # 2 seconds at 16 kHz, allow small decoder padding slack.
    assert 30000 <= len(audio) <= 34000
    assert np.abs(audio).max() > 0.1  # real signal, not silence


def test_decode_audio_ffmpeg_rejects_missing_file(tmp_path):
    with pytest.raises(RuntimeError):
        _decode_audio_ffmpeg(tmp_path / "nope.mp4")
