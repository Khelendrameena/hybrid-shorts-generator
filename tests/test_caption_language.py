"""Caption-language setting (user request 2026-11-11): the user chooses the
language of the captions AND of the Short's own text (title/hook), separate
from the spoken language. Translation is local (Ollama); any failure must
keep the original captions and never break a render."""
from backend.config import settings
from backend.generation import caption_translator as ct


def _segs(texts, lang_words=True):
    out = []
    t = 0.0
    for i, tx in enumerate(texts):
        words = [{"word": w, "start": t + j * 0.3, "end": t + j * 0.3 + 0.25,
                  "probability": 0.95} for j, w in enumerate(tx.split())]
        out.append({"id": i, "start": t, "end": t + 2.0, "text": tx, "words": words,
                    "avg_logprob": -0.1, "no_speech_prob": 0.0, "speaker_turn": 0})
        t += 2.5
    return out


EN = _segs(["This is the truth about money", "Nobody tells you this secret"])
HI_DEV = _segs(["यह बात बिल्कुल सच है", "कोई आपको यह नहीं बताता"])
HI_ROMAN = _segs(["ye baat bilkul sach hai", "koi aapko ye nahi batata"])


def test_needs_translation_matrix():
    assert ct.needs_translation(EN, "en", "hindi") is True
    assert ct.needs_translation(EN, "en", "english") is False
    assert ct.needs_translation(HI_DEV, "hi", "english") is True
    assert ct.needs_translation(HI_DEV, "hi", "hindi") is False       # already Devanagari
    assert ct.needs_translation(HI_DEV, "hi", "hinglish") is True     # transliteration chahiye
    assert ct.needs_translation(HI_ROMAN, "hi", "hinglish") is False  # already Roman Hindi
    assert ct.needs_translation(HI_ROMAN, "hi", "hindi") is True      # script badalna hai
    assert ct.needs_translation(EN, "en", "auto") is False
    assert ct.needs_translation([], "en", "hindi") is False


def test_metadata_language_mapping():
    assert ct.metadata_language("hindi") == "Hindi"
    assert ct.metadata_language("english") == "English"
    assert ct.metadata_language("hinglish") == "Hinglish"
    assert ct.metadata_language("auto") is None


def _prefix_chat(lines, target):
    return [f"[{target['name']}] {ln}" for ln in lines]


def test_translate_segments_success_keeps_timing():
    out, note = ct.translate_segments(EN, "hindi", chat_fn=_prefix_chat)
    assert [s["text"] for s in out] == [f"[Hindi] {s['text']}" for s in EN]
    assert "translate ho gaye" in note
    for orig, new in zip(EN, out):  # timing untouched, words re-synthesised
        assert new["start"] == orig["start"] and new["end"] == orig["end"]
        assert [w["word"] for w in new["words"]] == new["text"].split()
        assert new["translated_to"] == "Hindi"


def test_translate_segments_wrong_count_falls_back_to_original():
    def bad_chat(lines, target):
        return ["sirf ek line"]  # count mismatch, twice -> give up

    out, note = ct.translate_segments(EN, "english", chat_fn=bad_chat)
    assert out is EN  # the ORIGINAL list object comes back
    assert "original hi rahe" in note


def test_settings_api_accepts_caption_language():
    from fastapi.testclient import TestClient

    from backend.main import app

    c = TestClient(app)
    old = settings.caption_language
    try:
        r = c.post("/api/settings", json={"caption_language": "hinglish"})
        assert r.status_code == 200 and r.json()["caption_language"] == "hinglish"
        r = c.post("/api/settings", json={"caption_language": "french"})
        assert r.json()["caption_language"] == "hinglish"  # invalid ignored
    finally:
        settings.caption_language = old
