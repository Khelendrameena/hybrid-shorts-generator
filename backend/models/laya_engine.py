"""Model A — LAYA Decision Intelligence Engine.

REALITY CHECK (verified from the model card, docs/LAYA_RESEARCH.md):
Laya is NOT a generative LLM and NOT multimodal. `convaiinnovations/laya-multilingual`
is a 322M-param mmBERT-base encoder + decision head that takes a text STATE plus
TYPED QUESTIONS and returns typed answers with probabilities in ONE forward pass:
  - choice : pick one of named options   -> answers[q]["choice"], ["probabilities"]
  - score  : ordered levels              -> distribution over levels (weakest type)
  - noul   : P(true) for a proposition   -> answers[q]["noul"]

So this engine does exactly what Laya supports: it asks Laya typed questions
about each candidate transcript window and maps the returned probabilities to
the 0–100 component scores. It never asks Laya about video frames — visual
suitability comes from OpenCV/audio features (feature_extractor.py).

Calibration honesty: the model card states the multilingual checkpoint ships
uncalibrated and over-confident, and is near-chance zero-shot on some workflow
benchmarks. Production rule here: final component = 0.6 * Laya + 0.4 * heuristic
when Laya is live; 1.0 * heuristic (clearly labelled) when Laya is not installed
or fails to load. Either way the pipeline works and the engine name is recorded
on every clip so nothing is faked.
"""
from __future__ import annotations

import os

os.environ.setdefault("USE_TF", "0")  # model-card gotcha: TF probe can deadlock load

from ..config import settings
from ..analysis.feature_extractor import clamp, extract_features
from .manager import model_manager

# The typed question set — defined once, under Laya's limits (<20 choice options,
# short criteria; candidate windows are << the 1024-token budget).
QUESTIONS: dict = {
    "hook": {"type": "noul",
             "instructions": "Does `body` open with a strong hook — a question, surprising claim, bold statement or curiosity gap in its first sentence?"},
    "hook_ab": {"type": "choice",
                "instructions": "Is the opening of `body` a strong hook for a short video?",
                "criteria": {"A": "yes — strong hook, grabs attention immediately",
                             "B": "no — weak, slow or confusing opening"}},
    "emotion_level": {"type": "score",
                      "instructions": "How emotionally intense is `body`?",
                      "criteria": ["low", "medium", "high", "very_high"]},
    "category": {"type": "choice",
                 "instructions": "What is the dominant appeal of `body` for a short video?",
                 "criteria": {
                     "funny": "humour, jokes, laughter, playful banter",
                     "emotional": "personal feelings, touching, sad, heartfelt moments",
                     "educational": "facts, explanations, how-to, learning",
                     "controversial": "debate, strong opinions, disagreement, myths challenged",
                     "surprising": "unexpected revelations, twists, shocking facts",
                     "storytelling": "a narrative, anecdote or personal story with a payoff",
                     "neutral": "none of the above stands out"}},
    "information": {"type": "noul",
                    "instructions": "Does `body` contain a concrete fact, explanation, tip or insight the viewer learns from?"},
    "standalone": {"type": "noul",
                   "instructions": "Can a new viewer understand `body` fully without watching what came before it?"},
    "complete": {"type": "noul",
                 "instructions": "Does `body` finish its thought or story with a conclusion, answer or payoff instead of cutting off mid-idea?"},
    "clarity": {"type": "noul",
                "instructions": "Is the speech in `body` clear, fluent and easy to follow, without rambling or heavy repetition?"},
}


def _noul_prob(ans: dict) -> float | None:
    if not isinstance(ans, dict):
        return None
    for k in ("noul", "probability", "p_true", "value"):
        v = ans.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _choice_prob(ans: dict, option: str) -> float | None:
    if not isinstance(ans, dict):
        return None
    probs = ans.get("probabilities") or ans.get("probs") or {}
    if isinstance(probs, dict) and option in probs:
        return float(probs[option])
    if ans.get("choice") == option:
        conf = ans.get("answer_confidence") or ans.get("confidence")
        return float(conf) if isinstance(conf, (int, float)) else 0.7
    return None


def _score_expected(ans: dict, levels: list[str]) -> float | None:
    """Expected level → 0..100. Handles distribution dicts, numeric scores,
    and string levels — Laya versions differ slightly in field names."""
    if not isinstance(ans, dict):
        return None
    probs = ans.get("probabilities") or ans.get("probs") or {}
    if isinstance(probs, dict) and probs:
        tot, exp = 0.0, 0.0
        for i, lv in enumerate(levels):
            p = probs.get(lv)
            if isinstance(p, (int, float)):
                exp += i * float(p)
                tot += float(p)
        if tot > 0:
            return exp / tot / max(1, len(levels) - 1) * 100.0
    for k in ("expected_score", "score", "value"):
        v = ans.get(k)
        if isinstance(v, (int, float)):
            # numeric score is an index (0-based or 1-based) in Laya's schema
            idx = float(v)
            if idx >= 1 and idx <= len(levels):
                idx -= 1 if idx == len(levels) or True else 0
            return clamp(idx / max(1, len(levels) - 1) * 100.0)
        if isinstance(v, str) and v in levels:
            return levels.index(v) / max(1, len(levels) - 1) * 100.0
    return None


class LayaEngine:
    def __init__(self, model_id: str | None = None):
        self.model_id = model_id or settings.laya_model_id
        self._agent = None
        self._load_error: str | None = None
        self.engine_name = "laya"  # flips to "heuristic-fallback" if load fails

    # -- lifecycle ---------------------------------------------------------
    def available(self) -> tuple[bool, str]:
        try:
            import laya  # noqa: F401
            return True, "laya package installed"
        except Exception as e:
            return False, f"laya package not installed ({e}). Install: pip install laya"

    def load(self) -> bool:
        if self._agent is not None:
            return True
        ok, reason = self.available()
        if not ok or not settings.laya_enabled:
            self._load_error = reason if not ok else "LAYA_ENABLED=false"
            self.engine_name = "heuristic-fallback"
            return False
        model_manager.acquire("laya")
        try:
            import laya  # type: ignore

            try:
                self._agent = laya.load(self.model_id)
            except Exception:
                from laya import Router  # documented alternative entry point

                self._agent = Router(default="multilingual")
            self.engine_name = "laya"
            model_manager.register("laya", self)
            return True
        except Exception as e:
            self._load_error = f"Laya load failed: {str(e)[:300]}"
            self.engine_name = "heuristic-fallback"
            self._agent = None
            return False

    def unload(self):
        self._agent = None
        model_manager.release("laya")

    # -- raw Laya call ------------------------------------------------------
    def _predict(self, text: str) -> dict | None:
        if self._agent is None and not self.load():
            return None
        state = {"body": text}
        try:
            try:
                result = self._agent.predict(state, QUESTIONS, max_len=settings.laya_max_len)
            except TypeError:
                result = self._agent.predict(state, QUESTIONS)
            if isinstance(result, dict) and "answers" in result:
                return result["answers"]
        except Exception as e:
            self._load_error = f"Laya predict failed: {str(e)[:300]}"
        return None

    # -- public scoring -----------------------------------------------------
    def score_candidate(self, text: str, segments: list[dict] | None = None,
                        audio_energy: list[dict] | None = None,
                        start: float = 0.0, end: float = 0.0,
                        face_coverage: float = 0.0) -> dict:
        """Returns component scores 0–100 + category + reasons + provenance."""
        heur = extract_features(text, segments, audio_energy, start, end, face_coverage)
        answers = self._predict(text) if settings.laya_enabled else None

        if not answers:
            scores = {k: heur[k] for k in
                      ("hook_strength", "emotional_intensity", "information_value",
                       "standalone_context", "story_completeness", "speech_clarity",
                       "visual_suitability")}
            category = self._heuristic_category(heur, text)
            return {"scores": scores, "category": category, "engine": "heuristic-fallback",
                    "engine_note": self._load_error or "Laya unavailable — deterministic features only",
                    "reasons": self._reasons(scores, category, heur), "raw_laya": None}

        def blend(key: str, laya_val: float | None) -> float:
            if laya_val is None:
                return heur[key]
            return round(clamp(0.6 * laya_val + 0.4 * heur[key]), 1)

        hook_noul = _noul_prob(answers.get("hook", {}))
        hook_ab = _choice_prob(answers.get("hook_ab", {}), "A")
        # Model card: noul can under-report true → cross-check with the A/B choice.
        hook_vals = [v * 100 for v in (hook_noul, hook_ab) if v is not None]
        hook_laya = sum(hook_vals) / len(hook_vals) if hook_vals else None

        emotion_laya = _score_expected(answers.get("emotion_level", {}),
                                       ["low", "medium", "high", "very_high"])
        cat_ans = answers.get("category", {})
        category = cat_ans.get("choice") if isinstance(cat_ans, dict) else None
        if category not in ("funny", "emotional", "educational", "controversial",
                            "surprising", "storytelling", "neutral"):
            category = self._heuristic_category(heur, text)

        scores = {
            "hook_strength": blend("hook_strength", hook_laya),
            "emotional_intensity": blend("emotional_intensity", emotion_laya),
            "information_value": blend("information_value",
                                       (lambda v: v * 100 if v is not None else None)(_noul_prob(answers.get("information", {})))),
            "standalone_context": blend("standalone_context",
                                        (lambda v: v * 100 if v is not None else None)(_noul_prob(answers.get("standalone", {})))),
            "story_completeness": blend("story_completeness",
                                        (lambda v: v * 100 if v is not None else None)(_noul_prob(answers.get("complete", {})))),
            "speech_clarity": blend("speech_clarity",
                                    (lambda v: v * 100 if v is not None else None)(_noul_prob(answers.get("clarity", {})))),
            # Laya is text-only: visual suitability NEVER comes from Laya.
            "visual_suitability": heur["visual_suitability"],
        }
        return {"scores": scores, "category": category, "engine": "laya",
                "engine_note": f"{self.model_id} (mmBERT-base 322M) + heuristic calibration blend 60/40",
                "reasons": self._reasons(scores, category, heur), "raw_laya": answers}

    @staticmethod
    def _heuristic_category(heur: dict, text: str) -> str:
        low = (text or "").lower()
        if heur.get("has_laughter"):
            return "funny"
        if heur["information_value"] >= 65:
            return "educational"
        if heur["emotional_intensity"] >= 70:
            return "emotional"
        if "?" in text and heur["hook_strength"] >= 65:
            return "surprising"
        return "storytelling" if heur["story_completeness"] >= 65 else "neutral"

    @staticmethod
    def _reasons(scores: dict, category: str, heur: dict) -> list[str]:
        r = []
        if scores["hook_strength"] >= 70:
            r.append("Strong opening hook")
        if heur.get("has_question"):
            r.append("Opens/continues with a question — curiosity gap")
        if scores["emotional_intensity"] >= 70:
            r.append("High emotional intensity")
        if scores["information_value"] >= 70:
            r.append("High information value")
        if scores["story_completeness"] >= 70:
            r.append("Complete thought/story with payoff")
        if scores["standalone_context"] < 45:
            r.append("May need prior context")
        if heur.get("has_laughter"):
            r.append("Laughter detected")
        r.append(f"Category: {category}")
        return r
