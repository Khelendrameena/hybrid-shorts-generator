from backend.analysis.scoring import final_score, repetition_penalty_for

FULL = {"hook_strength": 100, "emotional_intensity": 100, "information_value": 100,
        "standalone_context": 100, "story_completeness": 100, "speech_clarity": 100,
        "visual_suitability": 100}


def test_all_hundred_is_hundred():
    assert final_score(FULL) == 100.0


def test_all_zero_is_zero():
    assert final_score({k: 0 for k in FULL}) == 0.0


def test_spec_formula_exact():
    # Only hook at 100 → 0.20 * 100 = 20 with default weights summing to 1.0
    s = dict(FULL, emotional_intensity=0, information_value=0, standalone_context=0,
             story_completeness=0, speech_clarity=0, visual_suitability=0)
    s["hook_strength"] = 100
    assert final_score(s) == 20.0


def test_repetition_penalty_subtracted():
    assert final_score(FULL, repetition_penalty=30) == 70.0


def test_repetition_penalty_identical_text_high():
    t = "this is a very interesting moment in the video today"
    assert repetition_penalty_for(t, t) >= 25


def test_repetition_penalty_unrelated_text_zero():
    assert repetition_penalty_for("alpha beta gamma delta epsilon zeta",
                                  "one two three four five six") == 0.0
