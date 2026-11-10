"""Deterministic transcript/visual features for a candidate window.

These features do two jobs:
 1. They are real scoring signals in their own right (speech clarity comes from
    Whisper confidences; visual suitability from faces/audio — Laya is TEXT-ONLY
    and is never credited with seeing frames).
 2. They calibrate/blend Laya's raw probabilities, which the Laya model card
    itself says ship UNCALIBRATED and over-confident (see docs/LAYA_RESEARCH.md).
"""
from __future__ import annotations

import re

EMOTION_WORDS = {
    "en": ["amazing", "shocking", "unbelievable", "wow", "crazy", "secret", "never",
           "love", "hate", "angry", "happy", "sad", "funny", "hilarious", "dangerous",
           "mistake", "wrong", "truth", "finally", "suddenly", " OMG".strip().lower()],
    "hi": ["bahut", "bilkul", "sach", "galat", "galti", "kabhi nahi", "hairan",
           "kamal", "maza", "has", "rona", "gussa", "pyar", "khatarnak", "raaz",
           "suno", "dekho", "socho", "samjho", "matlab"],
}
HOOK_OPENERS = re.compile(
    r"(^\s*(what if|did you know|stop |never |always |nobody |everyone |the truth|"
    r"kya aap|socho|dekho|suno|ek baat|agar |how to|why |listen))", re.I)
LAUGHTER = re.compile(r"(\[laughter\]|\(laughter\)|ha+ha+|😂|🤣)", re.I)
QUESTION = re.compile(r"\?")
NUMBER_FACT = re.compile(r"\b\d+(\.\d+)?\s*(%|percent|crore|lakh|hazaar|thousand|million|billion|rs|₹|saal|years?|days?)?\b", re.I)


def clamp(v: float) -> float:
    return max(0.0, min(100.0, float(v)))


def extract_features(text: str, segments: list[dict] | None = None,
                       audio_energy: list[dict] | None = None,
                       start: float = 0.0, end: float = 0.0,
                       face_coverage: float = 0.0) -> dict:
    t = (text or "").strip()
    low = t.lower()
    words = t.split()
    n = max(1, len(words))
    first_sentence = re.split(r"[.!?।]", t)[0] if t else ""

    hook = 30.0
    if QUESTION.search(first_sentence):
        hook += 25
    if HOOK_OPENERS.search(first_sentence):
        hook += 25
    if NUMBER_FACT.search(first_sentence):
        hook += 10
    if len(first_sentence.split()) <= 14 and first_sentence:
        hook += 10  # short punchy opening

    emo_hits = sum(low.count(w) for lst in EMOTION_WORDS.values() for w in lst)
    emotion = clamp(25 + emo_hits * 9 + (18 if LAUGHTER.search(t) else 0) + low.count("!") * 4)

    info = clamp(30 + len(NUMBER_FACT.findall(t)) * 12
                 + (20 if re.search(r"(because|kyunki|isiliye|reason|matlab|means|example|jaise)", low) else 0)
                 + min(20, n / 6))

    standalone = 55.0
    if re.search(r"^(so|and|but|aur|lekin|isiliye|then)\b", low):
        standalone -= 25  # starts mid-thought
    if re.search(r"\b(this|that|it|ye|wo|usne|iska)\b", first_sentence.lower()) and len(first_sentence.split()) < 5:
        standalone -= 10
    if QUESTION.search(t) or HOOK_OPENERS.search(first_sentence):
        standalone += 15
    standalone = clamp(standalone)

    last = t.rstrip()
    completeness = 40.0
    if last.endswith((".", "!", "?", "।")):
        completeness += 30
    if re.search(r"(that'?s (why|how)|isiliye|conclusion|finally|aakhir|answer is|jawab|so remember|yaad rakho)", low):
        completeness += 20
    if re.search(r"(and then|aur phir|so,|toh,)\s*$", low):
        completeness -= 25
    completeness = clamp(completeness)

    # Speech clarity from Whisper segment confidences when available.
    clarity = 60.0
    if segments:
        confs, nospeech = [], []
        for s in segments:
            ws = s.get("words") or []
            confs += [w.get("probability", 0) for w in ws]
            nospeech.append(s.get("no_speech_prob", 0))
        if confs:
            clarity = clamp(sum(confs) / len(confs) * 100)
        if nospeech and sum(nospeech) / len(nospeech) > 0.4:
            clarity = clamp(clarity - 25)

    # Visual suitability: faces present + non-black, energetic audio. NOT from Laya.
    visual = clamp(35 + face_coverage * 45)
    if audio_energy:
        rows = [r for r in audio_energy if start <= r["time"] <= end]
        if rows:
            avg = sum(r["rms"] for r in rows) / len(rows)
            silent_ratio = sum(1 for r in rows if r.get("silent")) / len(rows)
            visual = clamp(visual + min(20, avg * 160) - silent_ratio * 20)
            energy_boost = clamp(avg * 260)  # loud/expressive delivery helps emotion too
        else:
            energy_boost = 40.0
    else:
        energy_boost = 40.0
    emotion = clamp(emotion * 0.75 + energy_boost * 0.25)

    return {
        "hook_strength": round(clamp(hook), 1),
        "emotional_intensity": round(emotion, 1),
        "information_value": round(info, 1),
        "standalone_context": round(standalone, 1),
        "story_completeness": round(completeness, 1),
        "speech_clarity": round(clarity, 1),
        "visual_suitability": round(visual, 1),
        "word_count": n,
        "has_question": bool(QUESTION.search(t)),
        "has_laughter": bool(LAUGHTER.search(t)),
        "face_coverage": face_coverage,
    }
