from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.lexicon_segment import (
    gaps_from_segments,
    lexicon_hits_preview,
    lexicon_only_render,
    segment_with_lexicon,
)


@dataclass
class TranslateLineResult:
    conlang: str
    tts: str
    used_ai: bool
    note: str
    error: Optional[str] = None


def _whitepaper_brief(bundle: Dict[str, Any], max_chars: int = 1800) -> str:
    wp = bundle.get("whitepaper") or {}
    parts: List[str] = []
    sections = wp.get("sections") or {}
    for title in ("语法", "句法", "构词", "音位", "前言", "序言"):
        for k, v in sections.items():
            if title in k and isinstance(v, str) and v.strip():
                parts.append(f"## {k}\n{v.strip()[:800]}")
                break
    if not parts:
        raw = "\n".join(f"{k}\n{v[:400]}" for k, v in list(sections.items())[:6] if isinstance(v, str))
        parts.append(raw)
    text = "\n\n".join(parts)
    return text[:max_chars] if text else "（尚未解析白皮书，请将白皮书导入并重新解析。）"


def _anchors_preview(bundle: Dict[str, Any], max_items: int = 12) -> str:
    anchors = bundle.get("anchors") or {}
    if not isinstance(anchors, dict):
        return ""
    lines: List[str] = []
    for i, (k, v) in enumerate(anchors.items()):
        if i >= max_items:
            lines.append("…")
            break
        lines.append(f"{k} ⇒ {v}")
    return "\n".join(lines)


def _build_user_prompt(
    *,
    source: str,
    segments_preview: str,
    gaps: List[str],
    whitepaper: str,
    anchors: str,
) -> str:
    gaps_txt = "、".join(gaps) if gaps else "（无）"
    anchor_block = f"翻译历史锚定（节选）：\n{anchors}\n\n" if anchors.strip() else ""
    return (
        "你是专业的人工自创语（conlang）翻译助手。\n"
        "请严格根据白皮书中的音系、语法与构词约束输出；"
        "对「词表已给的片段」请尽量保持与词表一致。\n\n"
        f"{anchor_block}"
        f"白皮书与规则（节选）：\n{whitepaper}\n\n"
        f"中文原句：\n{source}\n\n"
        f"词表可直接覆盖的片段（节选）：\n{segments_preview}\n\n"
        f"词表未能覆盖、需要你处理的片段：{gaps_txt}\n\n"
        "请输出两行纯文本，不要加序号或解释：\n"
        "第1行：整句自创语（将词表外部分补全为与词表风格一致的整句）。\n"
        "第2行：对应整句的 TTS 友好音译（便于语音合成朗读）。"
    )


def _parse_two_lines(response: str) -> Tuple[str, str]:
    raw = (response or "").strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if len(lines) >= 2:
        return lines[0], lines[1]
    if len(lines) == 1:
        return lines[0], lines[0]
    return "", ""


def _apply_tts_map(conlang: str, tts_map: Dict[str, str]) -> str:
    if not conlang or not tts_map:
        return conlang
    result = conlang
    for word, spell in sorted(tts_map.items(), key=lambda kv: len(kv[0]), reverse=True):
        if word and word in result:
            result = result.replace(word, spell)
    return result


def _call_claude(api_key: str, model: str, prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    parts: List[str] = []
    for block in getattr(msg, "content", None) or []:
        t = getattr(block, "text", None)
        if t is not None:
            parts.append(t)
        elif isinstance(block, dict) and block.get("text"):
            parts.append(str(block["text"]))
    return "".join(parts).strip()


def _call_gemini(api_key: str, model: str, prompt: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    gm = genai.GenerativeModel(model)
    resp = gm.generate_content(prompt)
    text = getattr(resp, "text", None)
    if text:
        return str(text).strip()
    if getattr(resp, "candidates", None):
        parts = []
        for c in resp.candidates:
            content = getattr(c, "content", None)
            p = getattr(content, "parts", None) if content else None
            if p:
                for part in p:
                    t = getattr(part, "text", None)
                    if t:
                        parts.append(t)
        return "\n".join(parts).strip()
    return ""


def translate_line(
    settings: Dict[str, Any],
    bundle: Dict[str, Any],
    source_line: str,
) -> TranslateLineResult:
    """单句：词表最长匹配 → 词库外可选 AI 补全。"""
    line = source_line.strip()
    if not line:
        return TranslateLineResult("", "", False, "")

    lexicon = bundle.get("lexicon") or {}
    if not isinstance(lexicon, dict):
        lexicon = {}
    lexicon = {str(k): str(v) for k, v in lexicon.items() if str(k).strip()}

    tts_map = bundle.get("tts_map") or {}
    if not isinstance(tts_map, dict):
        tts_map = {}
    tts_map = {str(k): str(v) for k, v in tts_map.items() if str(k).strip()}

    segments = segment_with_lexicon(line, lexicon)
    gaps = gaps_from_segments(segments)
    draft = lexicon_only_render(segments, lexicon)

    enabled = bool(settings.get("enabled"))
    provider = str(settings.get("provider") or "claude").lower()
    oov_only = bool(settings.get("ai_for_oov_only", True))

    if not enabled:
        tts = _apply_tts_map(draft.replace("⟨", "").replace("⟩", ""), tts_map)
        note = "（AI 未启用，仅词表拼接；⟨⟩ 内为词表外字词）"
        return TranslateLineResult(draft, tts, False, note)

    need_ai = bool(gaps) or not oov_only
    if not need_ai:
        tts = _apply_tts_map(draft.replace("⟨", "").replace("⟩", ""), tts_map)
        return TranslateLineResult(
            draft.replace("⟨", "").replace("⟩", ""),
            tts,
            False,
            "（词表全覆盖，未调用 AI）",
        )

    if provider == "claude":
        key = str(settings.get("claude_api_key") or "").strip()
        model = str(settings.get("claude_model") or "claude-sonnet-4-20250514").strip()
    else:
        key = str(settings.get("gemini_api_key") or "").strip()
        model = str(settings.get("gemini_model") or "gemini-2.0-flash").strip()

    if not key:
        return TranslateLineResult(
            draft,
            _apply_tts_map(draft, tts_map),
            False,
            "",
            error="已启用 AI，但未填写当前提供商的 API Key。请在「工具 → AI 辅助翻译设置」中配置。",
        )

    prompt = _build_user_prompt(
        source=line,
        segments_preview=lexicon_hits_preview(segments, lexicon),
        gaps=gaps,
        whitepaper=_whitepaper_brief(bundle),
        anchors=_anchors_preview(bundle),
    )

    try:
        if provider == "claude":
            raw = _call_claude(key, model, prompt)
        elif provider == "gemini":
            raw = _call_gemini(key, model, prompt)
        else:
            return TranslateLineResult(
                draft,
                _apply_tts_map(draft, tts_map),
                False,
                "",
                error=f"未知提供商：{provider}",
            )
    except ImportError as exc:
        return TranslateLineResult(
            draft,
            _apply_tts_map(draft, tts_map),
            False,
            "",
            error=f"缺少依赖：{exc}。请执行：pip install anthropic google-generativeai",
        )
    except Exception as exc:
        return TranslateLineResult(
            draft,
            _apply_tts_map(draft, tts_map),
            False,
            "",
            error=f"AI 请求失败：{exc}",
        )

    conlang, tts_ai = _parse_two_lines(raw)
    if not conlang:
        return TranslateLineResult(
            draft,
            _apply_tts_map(draft, tts_map),
            True,
            "",
            error="AI 返回为空或无法解析，请检查模型与网络。",
        )

    note = f"（已使用 {provider.upper()} 补全词表外内容）"
    return TranslateLineResult(conlang.strip(), tts_ai.strip() or _apply_tts_map(conlang, tts_map), True, note)


def translate_multiline(
    settings: Dict[str, Any],
    bundle: Dict[str, Any],
    text: str,
) -> Tuple[str, str, str]:
    """多行：逐非空行翻译，返回 (整段自创语, 整段TTS, 附注/错误聚合)。"""
    lines = text.splitlines()
    outs_c: List[str] = []
    outs_t: List[str] = []
    notes: List[str] = []
    errors: List[str] = []

    for raw in lines:
        if not raw.strip():
            outs_c.append("")
            outs_t.append("")
            continue
        res = translate_line(settings, bundle, raw)
        outs_c.append(res.conlang)
        outs_t.append(res.tts)
        if res.note:
            notes.append(res.note)
        if res.error:
            errors.append(res.error)

    cjoined = "\n".join(outs_c)
    tjoined = "\n".join(outs_t)
    tail = ""
    if errors:
        tail = "\n\n" + "\n".join(errors[:3])
        if len(errors) > 3:
            tail += "\n…"
    elif notes:
        uniq = sorted(set(notes))
        tail = "\n" + uniq[0] if uniq else ""
    return cjoined, tjoined, tail.strip()
