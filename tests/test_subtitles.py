from backend.rendering.subtitle_engine import build_ass, build_srt, group_words, words_for_range


def _segments():
    words = []
    t = 10.0
    for w in "hello world this is a test of subtitles".split():
        words.append({"word": w, "start": t, "end": t + 0.4, "probability": 0.9})
        t += 0.45
    return [{"id": 0, "start": 10.0, "end": t, "text": "hello world", "words": words}]


def test_words_are_clip_relative():
    ws = words_for_range(_segments(), 10.0, 14.0)
    assert ws and ws[0]["start"] == 0.0
    assert all(w["end"] <= 4.0 for w in ws)


def test_grouping_limits():
    ws = words_for_range(_segments(), 10.0, 14.0)
    groups = group_words(ws, max_words=3)
    assert all(len(g["words"]) <= 3 for g in groups)


def test_ass_and_srt_build():
    ws = words_for_range(_segments(), 10.0, 14.0)
    ass = build_ass(ws, "dynamic")
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "Dialogue:" in ass
    srt = build_srt(ws)
    assert "-->" in srt and "hello" in srt
