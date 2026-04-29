from __future__ import annotations

from typing import Dict, List, Tuple

Segment = Tuple[str, str]


def segment_with_lexicon(text: str, lexicon: Dict[str, str]) -> List[Segment]:
    """按最长匹配将中文切开为词表命中 (lex) 与词表外 (gap) 片段。"""
    if not text:
        return []
    keys = sorted((k for k in lexicon if k), key=len, reverse=True)
    i = 0
    n = len(text)
    segments: List[Segment] = []
    while i < n:
        matched = False
        for k in keys:
            if text.startswith(k, i):
                segments.append(("lex", k))
                i += len(k)
                matched = True
                break
        if matched:
            continue
        ch = text[i]
        if segments and segments[-1][0] == "gap":
            segments[-1] = ("gap", segments[-1][1] + ch)
        else:
            segments.append(("gap", ch))
        i += 1
    return segments


def gaps_from_segments(segments: List[Segment]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for kind, s in segments:
        if kind != "gap":
            continue
        t = s.strip()
        if not t:
            continue
        if t not in seen:
            seen.add(t)
            out.append(s)
    return out


def lexicon_only_render(segments: List[Segment], lexicon: Dict[str, str]) -> str:
    parts: List[str] = []
    for kind, s in segments:
        if kind == "lex":
            parts.append(lexicon.get(s, f"⟨{s}⟩"))
        else:
            parts.append(f"⟨{s}⟩")
    return "".join(parts)


def lexicon_hits_preview(
    segments: List[Segment],
    lexicon: Dict[str, str],
    *,
    max_items: int = 24,
) -> str:
    lines: List[str] = []
    for kind, s in segments:
        if kind != "lex":
            continue
        if s in lexicon:
            lines.append(f"{s} → {lexicon[s]}")
        if len(lines) >= max_items:
            lines.append("…")
            break
    return "\n".join(lines) if lines else "（本句无词表直接命中）"
