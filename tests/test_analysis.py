from backend.analysis.deduplication import deduplicate, time_iou
from backend.analysis.timestamp_optimizer import optimize


def test_time_iou():
    assert time_iou(0, 10, 0, 10) == 1.0
    assert time_iou(0, 10, 20, 30) == 0.0
    assert abs(time_iou(0, 10, 5, 15) - (5 / 15)) < 1e-6


def test_dedup_keeps_higher_score():
    clips = [
        {"id": "a", "start": 0, "end": 30, "score": 50},
        {"id": "b", "start": 2, "end": 32, "score": 90},
        {"id": "c", "start": 100, "end": 130, "score": 70},
    ]
    kept = deduplicate(clips)
    ids = {c["id"] for c in kept}
    assert ids == {"b", "c"}


def _segments():
    segs = []
    t = 0.0
    words_all = "What if everything you knew was wrong? This one fact changes money forever. Let me explain it clearly now. Most people never learn this simple truth about saving.".split()
    words = []
    for w in words_all:
        words.append({"word": w, "start": round(t, 2), "end": round(t + 0.4, 2), "probability": 0.95})
        t += 0.45
    segs.append({"id": 0, "start": 0.0, "end": t, "text": " ".join(words_all), "words": words,
                 "avg_logprob": -0.1, "no_speech_prob": 0.01, "speaker_turn": 0})
    return segs


def test_optimizer_never_mid_word_and_within_bounds():
    segs = _segments()
    start, end, notes = optimize(3.13, 12.0, segs, video_duration=30.0)
    word_starts = {round(w["start"], 2) for s in segs for w in s["words"]}
    # start must be a word start minus padding (0.4 default) or 0
    assert start >= 0
    assert any(abs(start - (ws - 0.4)) < 0.02 for ws in word_starts) or start == 0.0
    assert end <= 30.0 and end > start


def test_optimizer_extends_to_sentence_end():
    segs = _segments()
    start, end, notes = optimize(0.0, 5.0, segs, video_duration=30.0)
    # window cut at 5s is mid-sentence; optimizer should extend to a sentence end
    assert end > 5.0
