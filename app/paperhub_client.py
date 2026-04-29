"""
PaperHub AI 客户端模块。

使用 OpenAI SDK（openai 库）与 PaperHub 平台通信：
  - 服务地址：https://tc-paperhub.diezhi.net/v1
  - 协议：OpenAI Chat Completions（兼容 OpenAI SDK）
  - 认证：Bearer Token（llm_api 类型 API Key）

公开接口：
  test_paperhub_connection(api_key, base_url, model) -> (ok: bool, message: str)
  translate_with_paperhub(settings, bundle, text)   -> (conlang, tts, tail)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.lexicon_segment import (
    gaps_from_segments,
    lexicon_hits_preview,
    segment_with_lexicon,
)


# ---------------------------------------------------------------------------
# 提示词构建（与 ai_client 保持一致风格）
# ---------------------------------------------------------------------------

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
        raw = "\n".join(
            f"{k}\n{v[:400]}"
            for k, v in list(sections.items())[:6]
            if isinstance(v, str)
        )
        parts.append(raw)
    text = "\n\n".join(parts)
    if not text:
        return "（尚未导入白皮书，请先导入并重新解析。）"
    return text[:max_chars]


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


def _build_prompt(
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


# ---------------------------------------------------------------------------
# PaperHub API 调用
# ---------------------------------------------------------------------------

def _call_paperhub(
    api_key: str,
    base_url: str,
    model: str,
    prompt: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    reasoning_enabled: bool = True,
) -> str:
    """调用 PaperHub Chat Completions 接口，返回模型文本响应。"""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImportError(
            "缺少 openai 包，请执行：pip install openai"
        ) from exc

    client = OpenAI(api_key=api_key, base_url=base_url)

    create_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # 思考模式（reasoning）—— 通过 extra_body 传递平台扩展参数
    if reasoning_enabled:
        create_kwargs["extra_body"] = {"reasoning": {"enabled": True}}

    resp = client.chat.completions.create(**create_kwargs)

    content: Optional[str] = None
    if resp.choices:
        msg = resp.choices[0].message
        content = getattr(msg, "content", None)
    return (content or "").strip()


# ---------------------------------------------------------------------------
# 测试连接
# ---------------------------------------------------------------------------

def test_paperhub_connection(
    api_key: str,
    base_url: str,
    model: str,
) -> Tuple[bool, str]:
    """
    向 PaperHub 发送最小请求验证 API Key 与连接是否有效。
    返回 (success, message)。
    """
    if not api_key.strip():
        return False, "API Key 不能为空，请先填写。"

    try:
        result = _call_paperhub(
            api_key=api_key,
            base_url=base_url,
            model=model,
            prompt="请回复「OK」（仅用于连接测试）",
            temperature=0.1,
            max_tokens=16,
            reasoning_enabled=False,
        )
        if result:
            return True, f"连接成功！模型响应：{result[:80]}"
        return False, "模型返回为空，请检查模型名称是否正确。"
    except ImportError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"连接失败：{exc}"


def fetch_paperhub_models(
    api_key: str,
    base_url: str,
) -> Tuple[bool, List[str], str]:
    """
    从 PaperHub 拉取可用模型列表。
    返回 (success, model_id_list, error_message)。

    使用 OpenAI SDK 的 client.models.list() 接口；
    列表按模型 ID 字母序排列，方便用户查找。
    """
    if not api_key.strip():
        return False, [], "请先填写 API Key。"
    try:
        from openai import OpenAI
    except ImportError:
        return False, [], "缺少 openai 包，请执行：pip install openai"

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.models.list()
        model_ids: List[str] = sorted(
            {m.id for m in response.data if m.id},
            key=str.lower,
        )
        if not model_ids:
            return False, [], "未获取到模型列表，请检查 API Key 权限。"
        return True, model_ids, ""
    except Exception as exc:
        return False, [], f"获取模型列表失败：{exc}"


# ---------------------------------------------------------------------------
# 翻译接口
# ---------------------------------------------------------------------------

def translate_line_paperhub(
    settings: Dict[str, Any],
    bundle: Dict[str, Any],
    source_line: str,
) -> Tuple[str, str, str]:
    """
    单行翻译。返回 (conlang, tts, tail)。
    tail 为错误信息或空字符串。
    """
    line = source_line.strip()
    if not line:
        return "", "", ""

    api_key = str(settings.get("paperhub_api_key") or "").strip()
    base_url = str(settings.get("paperhub_base_url") or "https://tc-paperhub.diezhi.net/v1")
    model = str(settings.get("paperhub_model") or "qwen3-max")
    reasoning = bool(settings.get("paperhub_reasoning_enabled", True))
    temperature = float(settings.get("paperhub_temperature", 0.7))
    max_tokens = int(settings.get("paperhub_max_tokens", 2048))

    if not api_key:
        return "", "", "未填写 PaperHub API Key，请在「设置 → PaperHub 设置」中配置。"

    lexicon = bundle.get("lexicon") or {}
    if not isinstance(lexicon, dict):
        lexicon = {}
    lexicon = {str(k): str(v) for k, v in lexicon.items() if k}

    segments = segment_with_lexicon(line, lexicon)
    gaps = gaps_from_segments(segments)

    prompt = _build_prompt(
        source=line,
        segments_preview=lexicon_hits_preview(segments, lexicon),
        gaps=gaps,
        whitepaper=_whitepaper_brief(bundle),
        anchors=_anchors_preview(bundle),
    )

    try:
        raw = _call_paperhub(
            api_key=api_key,
            base_url=base_url,
            model=model,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            reasoning_enabled=reasoning,
        )
    except ImportError as exc:
        return "", "", str(exc)
    except Exception as exc:
        return "", "", f"PaperHub 请求失败：{exc}"

    conlang, tts = _parse_two_lines(raw)
    if not conlang:
        return "", "", "PaperHub 返回为空，请检查模型与网络。"
    return conlang, tts, ""


def translate_multiline_paperhub(
    settings: Dict[str, Any],
    bundle: Dict[str, Any],
    text: str,
) -> Tuple[str, str, str]:
    """
    多行翻译：逐非空行调用 translate_line_paperhub，聚合结果。
    返回 (整段自创语, 整段TTS, 错误/附注)。
    """
    lines = text.splitlines()
    outs_c: List[str] = []
    outs_t: List[str] = []
    errors: List[str] = []

    for raw_line in lines:
        if not raw_line.strip():
            outs_c.append("")
            outs_t.append("")
            continue
        conlang, tts, tail = translate_line_paperhub(settings, bundle, raw_line)
        outs_c.append(conlang if conlang else raw_line)
        outs_t.append(tts if tts else raw_line)
        if tail:
            errors.append(tail)

    joined_c = "\n".join(outs_c)
    joined_t = "\n".join(outs_t)
    err_summary = ""
    if errors:
        unique = list(dict.fromkeys(errors))
        err_summary = "\n".join(unique[:3])
        if len(unique) > 3:
            err_summary += "\n…"
    return joined_c, joined_t, err_summary
