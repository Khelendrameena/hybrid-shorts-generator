"""YouTube-captions transcript source (user request 2026-11-10): videos that
already have captions on YouTube should take them from YouTube in seconds
instead of running Faster-Whisper; everything else keeps the Whisper path.
These tests are offline: parsing + track selection + a stubbed fetch."""
import json
import sys
import types

from backend.transcription import youtube_captions as yc


JSON3 = {
    "events": [
        {"tStartMs": 0, "dDurationMs": 1200, "segs": [{"utf8": "[♪♪♪]"}]},  # music marker -> skipped
        {"tStartMs": 0, "dDurationMs": 2000, "segs": [{"utf8": "Hello dosto, "}, {"utf8": "welcome\nback"}]},
        {"tStartMs": 2000, "dDurationMs": 1000},  # no segs -> skipped
        {"tStartMs": 3000, "dDurationMs": 2500, "segs": [{"utf8": "aaj hum ek nayi cheez seekhenge"}]},
        {"tStartMs": 8000, "dDurationMs": 2000, "segs": [{"utf8": "last line here"}]},
    ]
}

VTT = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000 align:start position:0%
Hello <b>dosto</b> welcome back

00:00:03.000 --> 00:00:05.500 align:start position:0%
second line here
"""


def test_parse_json3_segments_and_words():
    segs = yc.parse_json3(JSON3)
    assert [s["text"] for s in segs] == [
        "Hello dosto, welcome back", "aaj hum ek nayi cheez seekhenge", "last line here"]
    assert segs[0]["start"] == 0.0 and segs[0]["end"] == 2.0
    words = segs[0]["words"]
    assert [w["word"] for w in words] == ["Hello", "dosto,", "welcome", "back"]
    # synthetic word timings stay inside the segment and move forward
    assert words[0]["start"] == 0.0 and words[-1]["end"] <= 2.0
    assert all(a["end"] <= b["start"] + 0.001 for a, b in zip(words, words[1:]))
    assert all(w["probability"] == 0.9 for w in words)  # flagged as synthesised


def test_parse_vtt_segments():
    segs = yc.parse_vtt(VTT)
    assert [s["text"] for s in segs] == ["Hello dosto welcome back", "second line here"]
    assert segs[1]["start"] == 3.0 and segs[1]["end"] == 5.5


def _fmts(ext="json3"):
    return [{"ext": ext, "url": "https://example.invalid/track"}]


def test_pick_track_manual_beats_auto_and_pref_wins():
    info = {"subtitles": {"en": _fmts(), "hi": _fmts()},
            "automatic_captions": {"hi": _fmts()}}
    lang, kind, _ = yc.pick_track(info, preferred="hi")
    assert (lang, kind) == ("hi", "manual")
    lang, kind, _ = yc.pick_track(info)  # default order hi, en
    assert (lang, kind) == ("hi", "manual")


def test_pick_track_auto_original_only():
    # only a machine-translated track exists -> refuse (Whisper should run)
    info = {"subtitles": {}, "automatic_captions": {"fr": _fmts(), "de": _fmts()}}
    assert yc.pick_track(info) is None
    # original-language auto track is accepted
    info = {"subtitles": {}, "automatic_captions": {"en-orig": _fmts(), "fr": _fmts()}}
    lang, kind, _ = yc.pick_track(info)
    assert (lang, kind) == ("en-orig", "auto")


def test_fetch_with_stubbed_ytdlp_saves_whisper_schema(tmp_path, monkeypatch):
    track = tmp_path / "track.json3"
    track.write_text(json.dumps(JSON3), encoding="utf-8")

    class FakeYDL:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download=False):
            return {"subtitles": {"en": [{"ext": "json3", "url": track.as_uri()}]},
                    "automatic_captions": {}}

    stub = types.SimpleNamespace(YoutubeDL=FakeYDL)
    monkeypatch.setitem(sys.modules, "yt_dlp", stub)

    out = yc.fetch_youtube_captions("https://www.youtube.com/watch?v=x", tmp_path / "proj")
    assert out is not None
    assert out["source"] == "youtube_captions" and out["caption_kind"] == "manual"
    assert out["language"] == "en" and len(out["segments"]) == 3
    saved = json.loads((tmp_path / "proj" / "transcript.json").read_text(encoding="utf-8"))
    assert saved["full_text"].startswith("Hello dosto")
    assert (tmp_path / "proj" / "transcript.srt").exists()


def test_fetch_returns_none_without_tracks(tmp_path, monkeypatch):
    class FakeYDL:
        def __init__(self, opts): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def extract_info(self, url, download=False):
            return {"subtitles": {}, "automatic_captions": {}}

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FakeYDL))
    assert yc.fetch_youtube_captions("https://www.youtube.com/watch?v=x", tmp_path) is None
