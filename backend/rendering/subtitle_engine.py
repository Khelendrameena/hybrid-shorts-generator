"""Subtitle engine: builds ASS subtitles from WORD timestamps with per-word
highlighting (karaoke-style \\k + a highlighted 'active word' style pass),
plus plain SRT export. Four themes. Words are grouped into short caption
lines (max ~5 words / 1.6s) so captions never flood the vertical frame."""
from __future__ import annotations

THEMES = {
    "dynamic":     {"font": "Arial", "size": 64, "primary": "&H00FFFFFF", "highlight": "&H0000E5FF",
                    "outline": "&H00000000", "bold": 1, "border": 4, "shadow": 1},
    "classic":     {"font": "Arial", "size": 56, "primary": "&H00FFFFFF", "highlight": "&H00FFFFFF",
                    "outline": "&H00000000", "bold": 0, "border": 3, "shadow": 1},
    "minimal":     {"font": "Arial", "size": 50, "primary": "&H00FFFFFF", "highlight": "&H00A6F4FF",
                    "outline": "&H96000000", "bold": 0, "border": 2, "shadow": 0},
    "bold-yellow": {"font": "Arial", "size": 68, "primary": "&H0000E5FF", "highlight": "&H00FFFFFF",
                    "outline": "&H00000000", "bold": 1, "border": 5, "shadow": 1},
}


def _ass_time(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def words_for_range(segments: list[dict], start: float, end: float) -> list[dict]:
    """Clip-relative word list for [start, end]."""
    out = []
    for s in segments:
        for w in s.get("words") or []:
            if w["end"] > start and w["start"] < end:
                out.append({"word": w["word"].strip(),
                            "start": max(0.0, w["start"] - start),
                            "end": min(end - start, w["end"] - start)})
    return [w for w in out if w["word"]]


def group_words(words: list[dict], max_words: int = 5, max_dur: float = 1.6) -> list[dict]:
    groups, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["end"] - cur[0]["start"] > max_dur):
            groups.append({"start": cur[0]["start"], "end": cur[-1]["end"], "words": cur})
            cur = []
        cur.append(w)
    if cur:
        groups.append({"start": cur[0]["start"], "end": cur[-1]["end"], "words": cur})
    return groups


def _esc(text: str) -> str:
    return text.replace("\\", "").replace("{", "").replace("}", "").strip()


def build_ass(words: list[dict], theme_name: str = "dynamic",
              width: int = 1080, height: int = 1920) -> str:
    th = THEMES.get(theme_name, THEMES["dynamic"])
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{th['font']},{th['size']},{th['primary']},{th['highlight']},{th['outline']},&H64000000,{th['bold']},0,0,0,100,100,0,0,1,{th['border']},{th['shadow']},2,60,60,420,1
Style: Active,{th['font']},{th['size']},{th['highlight']},{th['highlight']},{th['outline']},&H64000000,{th['bold']},0,0,0,100,100,0,0,1,{th['border']},{th['shadow']},2,60,60,420,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for g in group_words(words):
        # One dialogue per word: full line shown, active word in Highlight colour
        # via inline override. Simple + robust across ffmpeg/libass versions.
        for i, w in enumerate(g["words"]):
            parts = []
            for j, gw in enumerate(g["words"]):
                txt = _esc(gw["word"])
                if j == i:
                    parts.append(f"{{\\c{th['highlight']}}}{txt}{{\\c{th['primary']}}}")
                else:
                    parts.append(txt)
            text = " ".join(parts)
            end = g["words"][i + 1]["start"] if i + 1 < len(g["words"]) else g["end"]
            lines.append(f"Dialogue: 0,{_ass_time(w['start'])},{_ass_time(max(end, w['end']))},Caption,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"


def build_srt(words: list[dict]) -> str:
    def fmt(t: float) -> str:
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    out = []
    for i, g in enumerate(group_words(words), 1):
        out.append(str(i))
        out.append(f"{fmt(g['start'])} --> {fmt(g['end'])}")
        out.append(" ".join(w["word"] for w in g["words"]))
        out.append("")
    return "\n".join(out)
