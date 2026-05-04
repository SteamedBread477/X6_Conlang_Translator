"""
PaperHub AI 翻译核心模块（阶段六）。

使用 OpenAI SDK（openai 库）与 PaperHub 平台通信：
  - 服务地址：https://tc-paperhub.diezhi.net/v1
  - 协议：OpenAI Chat Completions（兼容 OpenAI SDK）
  - 认证：Bearer Token（llm_api 类型 API Key）

三种翻译策略：
  - unmatched_only：仅在词汇未匹配时使用 AI（先规则翻译，再 AI 补全）
  - always：所有翻译都使用 AI
  - confirm：AI 生成候选，用户确认后采用

公开接口：
  test_paperhub_connection(api_key, base_url, model) -> (ok: bool, message: str)
  fetch_paperhub_models(api_key, base_url) -> (ok, model_ids, error)
  translate_with_paperhub(settings, bundle, text) -> PaperHubResult
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.lexicon_segment import (
    gaps_from_segments,
    lexicon_hits_preview,
    segment_with_lexicon,
)
from app.rule_translator import translate_multiline_rule


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class NewWord:
    """AI 创造的新词汇。"""
    chinese: str
    conlang: str
    ipa: str
    tts: str
    logic: str


@dataclass
class PaperHubResult:
    """PaperHub 翻译结果。"""
    conlang: str = ""
    tts: str = ""
    new_words: List[NewWord] = field(default_factory=list)
    strategy_used: str = ""
    error: str = ""
    raw_response: str = ""


# ---------------------------------------------------------------------------
# 提示词构建（阶段六：系统提示词 + 用户提示词，JSON 格式输出）
# ---------------------------------------------------------------------------

def _whitepaper_full(bundle: Dict[str, Any], max_chars: int = 3000) -> str:
    """提取白皮书全文（用于系统提示词，比 brief 更完整）。"""
    wp = bundle.get("whitepaper") or {}
    sections = wp.get("sections") or {}
    if not sections:
        # 尝试 raw_content（parse_whitepaper 可能存储）
        raw = wp.get("raw_content") or ""
        if raw:
            return raw[:max_chars]
        return "（尚未导入白皮书，请先导入并重新解析。）"

    parts: List[str] = []
    # 按优先级提取核心章节
    priority_keys = ["音位", "音系", "语音", "语法", "句法", "构词", "词法", "前言", "序言"]
    added: set[str] = set()
    for keyword in priority_keys:
        for k, v in sections.items():
            if keyword in k and k not in added and isinstance(v, str) and v.strip():
                parts.append(f"## {k}\n{v.strip()}")
                added.add(k)

    # 补充剩余章节
    for k, v in sections.items():
        if k not in added and isinstance(v, str) and v.strip():
            parts.append(f"## {k}\n{v.strip()[:600]}")

    text = "\n\n".join(parts)
    if not text:
        return "（白皮书内容为空，请先导入并重新解析。）"
    return text[:max_chars]


def _vocabulary_list(
    bundle: Dict[str, Any],
    input_text: Optional[str] = None,
    *,
    max_items: int = 80,
    extra_keys: Optional[List[str]] = None,
    core_quota: int = 200,
    hit_quota: int = 500,
    char_budget: int = 8000,
    retrieval_enabled: bool = True,
) -> str:
    """将词库格式化为 AI 可读的列表。

    两种模式：
      - retrieval_enabled=True 且 input_text 非空：走检索式注入，仅展示与
        input_text 相关的词条 + 核心词（L1）+ 命中词（L2）+ extra_keys（L3 会话热词）。
        附带元数据（词性/风格）。
      - 否则：回落到旧的"前 max_items 条 + 截断告知"全量截断模式（B 方案兜底）。
    """
    lexicon = bundle.get("lexicon") or {}
    if not isinstance(lexicon, dict):
        return "（词库尚未加载。）"
    lexicon = {str(k): str(v) for k, v in lexicon.items() if str(k).strip()}

    if not lexicon:
        return "（词库为空。）"

    if retrieval_enabled and (input_text or extra_keys):
        return _render_retrieved_vocab(
            bundle=bundle,
            lexicon=lexicon,
            input_text=input_text or "",
            extra_keys=extra_keys or [],
            core_quota=core_quota,
            hit_quota=hit_quota,
            char_budget=char_budget,
        )

    # ��全量截断模式（B 方案兜底，或用于无具体输入的旁路场景）
    lines: List[str] = []
    for i, (zh, con) in enumerate(lexicon.items()):
        if i >= max_items:
            lines.append(
                f"…（共 {len(lexicon)} 个词汇，已截断显示前 {max_items} 个，"
                f"如需完整词表参与，请在「PaperHub 设置」切换到更大 context 的模型）"
            )
            break
        lines.append(f"{zh} → {con}")
    return "\n".join(lines)


def _format_lex_line(zh: str, con: str, meta: Dict[str, Any]) -> str:
    """渲染单条词库展示行，附带元数据。"""
    extras: List[str] = []
    pos = meta.get("pos") if isinstance(meta, dict) else ""
    style = meta.get("style") if isinstance(meta, dict) else ""
    if pos:
        extras.append(str(pos))
    if style:
        extras.append(str(style))
    if extras:
        return f"{zh} → {con}  ({'/'.join(extras)})"
    return f"{zh} → {con}"


def _select_relevant_lexicon(
    bundle: Dict[str, Any],
    lexicon: Dict[str, str],
    input_text: str,
    extra_keys: List[str],
    *,
    core_quota: int,
    hit_quota: int,
) -> Tuple[List[str], int, int, int]:
    """挑选要塞进 prompt 的词条 zh-key 列表。

    返回 (selected_zh_list, total_lex_size, core_count, hit_count)。
    优先级：L1 核心词 > L2 输入命中词 + 会话热词 > L3 近义词。
    """
    meta_idx_raw = bundle.get("lexicon_meta") or {}
    meta_idx = meta_idx_raw if isinstance(meta_idx_raw, dict) else {}

    # L1: 核心词（core=True 优先；否则按 freq 取 Top-N）
    core_candidates = [
        (zh, int(m.get("freq") or 0))
        for zh, m in meta_idx.items()
        if isinstance(m, dict) and m.get("core") and zh in lexicon
    ]
    core_candidates.sort(key=lambda kv: kv[1], reverse=True)
    core_selected: List[str] = [zh for zh, _ in core_candidates[:core_quota]]
    core_set = set(core_selected)

    # 若 core 没填够，用 freq Top-N 补齐（仅在 freq>0 时启用，避免随机噪声）
    if len(core_selected) < core_quota:
        freq_candidates = [
            (zh, int(m.get("freq") or 0))
            for zh, m in meta_idx.items()
            if isinstance(m, dict) and zh not in core_set and zh in lexicon
            and int(m.get("freq") or 0) > 0
        ]
        freq_candidates.sort(key=lambda kv: kv[1], reverse=True)
        for zh, _ in freq_candidates:
            if len(core_selected) >= core_quota:
                break
            core_selected.append(zh)
            core_set.add(zh)

    # L2: 输入命中（基于词库做最长匹配） + 会话热词
    hit_set: List[str] = []
    seen_hit: set[str] = set()
    if input_text:
        segs = segment_with_lexicon(input_text, lexicon)
        for kind, s in segs:
            if kind == "lex" and s in lexicon and s not in core_set and s not in seen_hit:
                hit_set.append(s)
                seen_hit.add(s)
                if len(hit_set) >= hit_quota:
                    break
    for k in extra_keys:
        if k in lexicon and k not in core_set and k not in seen_hit:
            hit_set.append(k)
            seen_hit.add(k)
            if len(hit_set) >= hit_quota:
                break

    # L3: 近义词（基于命中词的 synonyms 字段反查），做轻量扩展
    syn_set: List[str] = []
    syn_seen: set[str] = set()
    for zh in hit_set:
        m = meta_idx.get(zh)
        if not isinstance(m, dict):
            continue
        for syn in (m.get("synonyms") or []):
            if (
                isinstance(syn, str)
                and syn in lexicon
                and syn not in core_set
                and syn not in seen_hit
                and syn not in syn_seen
            ):
                syn_set.append(syn)
                syn_seen.add(syn)

    selected = core_selected + hit_set + syn_set
    return selected, len(lexicon), len(core_selected), len(hit_set)


def _render_retrieved_vocab(
    *,
    bundle: Dict[str, Any],
    lexicon: Dict[str, str],
    input_text: str,
    extra_keys: List[str],
    core_quota: int,
    hit_quota: int,
    char_budget: int,
) -> str:
    """检索 + 渲染（含字符预算兜底截断）。"""
    meta_idx_raw = bundle.get("lexicon_meta") or {}
    meta_idx = meta_idx_raw if isinstance(meta_idx_raw, dict) else {}

    selected, total_size, core_count, hit_count = _select_relevant_lexicon(
        bundle=bundle,
        lexicon=lexicon,
        input_text=input_text,
        extra_keys=extra_keys,
        core_quota=core_quota,
        hit_quota=hit_quota,
    )

    if not selected:
        return (
            f"（词库共 {total_size} 个词汇，本句未命中且无核心词；"
            f"若结果不佳，可在词库中标记 core=true 增加核心词常驻。）"
        )

    lines: List[str] = []
    used_chars = 0
    rendered = 0
    truncated = False
    for zh in selected:
        con = lexicon.get(zh, "")
        if not con:
            continue
        line = _format_lex_line(zh, con, meta_idx.get(zh, {}))
        # +1 for newline
        if used_chars + len(line) + 1 > char_budget:
            truncated = True
            break
        lines.append(line)
        used_chars += len(line) + 1
        rendered += 1

    summary_parts = [f"词库共 {total_size}", f"已选 {rendered}（核心 {core_count} + 命中 {hit_count}）"]
    if truncated:
        summary_parts.append(
            f"超字符预算 {char_budget} 已截断，建议在「PaperHub 设置」切换更大 context 模型"
        )
    suffix = "（" + "；".join(summary_parts) + "）"
    return "\n".join(lines) + "\n" + suffix


def _translation_history_samples(bundle: Dict[str, Any], max_items: int = 12) -> str:
    """提取翻译历史锚定样本。"""
    anchors = bundle.get("anchors") or {}
    if not isinstance(anchors, dict):
        return ""
    lines: List[str] = []
    for i, (k, v) in enumerate(anchors.items()):
        if i >= max_items:
            lines.append("…")
            break
        lines.append(f"{k} ⇒ {v}")
    return "\n".join(lines) if lines else ""


def _build_system_prompt(
    bundle: Dict[str, Any],
    input_text: Optional[str] = None,
    *,
    extra_keys: Optional[List[str]] = None,
    retrieval_enabled: bool = True,
    core_quota: int = 200,
    hit_quota: int = 500,
    char_budget: int = 8000,
) -> str:
    """构建系统提示词（阶段六完整模板）。

    input_text：当前要翻译的中文。非空时启用检索式注入，仅展示相关词条。
    extra_keys：额外强制纳入的词条 zh-key（用于语言大师对话的会话热词）。
    retrieval_enabled：False 走旧的全量截断（B 方案兜底）。
    """
    whitepaper = _whitepaper_full(bundle)
    vocab = _vocabulary_list(
        bundle,
        input_text=input_text,
        extra_keys=extra_keys,
        retrieval_enabled=retrieval_enabled,
        core_quota=core_quota,
        hit_quota=hit_quota,
        char_budget=char_budget,
    )
    history = _translation_history_samples(bundle)

    history_block = ""
    if history.strip():
        history_block = f"\n【翻译历史】（用于保持一致性）\n{history}\n"

    return (
        "你是一个虚构语言翻译专家。请根据以下语言白皮书和词库，将中文翻译为该自创语。\n"
        "【重要规则】\n"
        "- 优先使用词库中已有的词汇，确保一致性\n"
        "- 词库中没有的词汇，请根据白皮书中的音位表和构词法创造新词\n"
        "- 遵循白皮书中的语法规则调整词序\n"
        "- 新创造的词汇请在输出中标注[NEW]\n"
        "- 输出格式必须严格遵循指定格式\n"
        "- 【断词规则】如果用户输入的中文中包含空格，空格表示用户手动断词/断句的边界。空格分隔的每个片段应作为一个整体词组翻译，不要将同一片段内的词拆开；不同片段之间在输出中也用空格分隔。如果用户输入没有空格，则由你自行理解断句断词。\n"
        f"\n【语言白皮书】\n{whitepaper}\n"
        f"\n【词库】\n{vocab}\n"
        f"{history_block}"
    )


def _build_user_prompt_full(chinese_text: str) -> str:
    """构建用户提示词（always 策略：完整翻译）。"""
    space_hint = ""
    if " " in chinese_text.strip():
        space_hint = (
            "\n【断词提示】原文中的空格是用户手动断词边界，请将空格分隔的每个片段作为一个整体词组翻译，"
            "不要拆开片段内的词；不同片段在自创语输出中也用空格分隔。\n"
        )
    return (
        f"请将以下中文翻译为自创语：\n"
        f"{space_hint}"
        f"【中文原文】\n{chinese_text}\n\n"
        "请按以下JSON格式输出（不要输出任何其他内容，不要加markdown标记）：\n"
        "{\n"
        "  \"conlang_text\": \"自创语文本\",\n"
        "  \"new_words\": [\n"
        "    {\n"
        "      \"chinese\": \"中文原词\",\n"
        "      \"conlang\": \"自创语\",\n"
        "      \"ipa\": \"IPA音标\",\n"
        "      \"tts\": \"TTS友好拼写\",\n"
        "      \"logic\": \"构词逻辑说明\"\n"
        "    }\n"
        "  ],\n"
        "  \"tts_phonetic\": \"完整TTS友好拼写\"\n"
        "}"
    )


def _build_user_prompt_unmatched(
    chinese_text: str,
    unmatched_words: List[str],
    rule_conlang: str,
) -> str:
    """构建用户提示词（unmatched_only 策略：仅补全未匹配词汇）。"""
    unmatched_txt = "、".join(unmatched_words) if unmatched_words else "（无）"
    space_hint = ""
    if " " in chinese_text.strip():
        space_hint = (
            "\n【断词提示】原文中的空格是用户手动断词边界，请将空格分隔的每个片段作为一个整体词组翻译，"
            "不要拆开片段内的词；不同片段在自创语输出中也用空格分隔。补全时也请保持原有的空格断词结构。\n"
        )
    return (
        f"请将以下中文中词库未覆盖的部分翻译为自创语，并与已有的规则翻译结果合并。\n"
        f"{space_hint}"
        f"【中文原文】\n{chinese_text}\n\n"
        f"【词库未覆盖的词汇】\n{unmatched_txt}\n\n"
        f"【词库已覆盖部分的翻译】\n{rule_conlang}\n\n"
        "请按以下JSON格式输出（不要输出任何其他内容，不要加markdown标记）：\n"
        "{\n"
        "  \"conlang_text\": \"完整的自创语文本（合并词库翻译与新创词汇）\",\n"
        "  \"new_words\": [\n"
        "    {\n"
        "      \"chinese\": \"中文原词\",\n"
        "      \"conlang\": \"自创语\",\n"
        "      \"ipa\": \"IPA音标\",\n"
        "      \"tts\": \"TTS友好拼写\",\n"
        "      \"logic\": \"构词逻辑说明\"\n"
        "    }\n"
        "  ],\n"
        "  \"tts_phonetic\": \"完整TTS友好拼写\"\n"
        "}"
    )


# ---------------------------------------------------------------------------
# JSON 响应解析
# ---------------------------------------------------------------------------

def _extract_json_from_response(raw: str) -> Optional[Dict[str, Any]]:
    """
    从 AI 响应中提取 JSON 对象。
    尝试多种方式：直接解析、提取 ```json``` 代码块、查找 { } 边界。
    """
    text = raw.strip()

    # 1. 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. 提取 ```json``` 代码块
    json_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_block_match:
        try:
            return json.loads(json_block_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. 查找最外层 { } 边界
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        candidate = brace_match.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 4. 尝试修复常见问题：多余逗号、缺少引号
    # 查找任何看起来像 JSON 的内容
    for start_idx in range(len(text)):
        if text[start_idx] == "{":
            # 向后查找匹配的 }
            depth = 0
            for end_idx in range(start_idx, len(text)):
                if text[end_idx] == "{":
                    depth += 1
                elif text[end_idx] == "}":
                    depth -= 1
                if depth == 0:
                    candidate = text[start_idx:end_idx + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        continue
                    break

    return None


def _parse_new_words(new_words_raw: Any) -> List[NewWord]:
    """解析 new_words 数组为 NewWord 对象列表。"""
    result: List[NewWord] = []
    if not isinstance(new_words_raw, list):
        return result
    for item in new_words_raw:
        if not isinstance(item, dict):
            continue
        nw = NewWord(
            chinese=str(item.get("chinese") or item.get("中文") or "").strip(),
            conlang=str(item.get("conlang") or item.get("自创语") or "").strip(),
            ipa=str(item.get("ipa") or item.get("IPA") or "").strip(),
            tts=str(item.get("tts") or item.get("TTS") or "").strip(),
            logic=str(item.get("logic") or item.get("构词逻辑") or item.get("构词逻辑说明") or "").strip(),
        )
        if nw.chinese and nw.conlang:
            result.append(nw)
    return result


def _parse_paperhub_response(raw: str) -> PaperHubResult:
    """
    解析 PaperHub AI 响应为结构化结果。
    如果 JSON 解析失败，尝试退化到两行纯文本模式。
    """
    data = _extract_json_from_response(raw)

    if data is not None:
        conlang_text = str(data.get("conlang_text") or data.get("自创语文本") or "").strip()
        tts_phonetic = str(data.get("tts_phonetic") or data.get("完整TTS友好拼写") or "").strip()
        new_words = _parse_new_words(data.get("new_words") or data.get("新词") or [])

        # 清理 [NEW] 标记
        clean_conlang = re.sub(r"\[NEW\]", "", conlang_text)

        return PaperHubResult(
            conlang=clean_conlang,
            tts=tts_phonetic,
            new_words=new_words,
            raw_response=raw,
        )

    # 退化：尝试解析两行纯文本（兼容旧格式）
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
    if len(lines) >= 2:
        return PaperHubResult(
            conlang=lines[0],
            tts=lines[1],
            raw_response=raw,
        )
    if len(lines) == 1:
        return PaperHubResult(
            conlang=lines[0],
            tts=lines[0],
            raw_response=raw,
        )

    return PaperHubResult(
        error="AI 响应无法解析为 JSON 或纯文本格式。请检查模型输出，或手动修正。",
        raw_response=raw,
    )


# ---------------------------------------------------------------------------
# PaperHub API 调用（带超时与错误处理，支持流式输出）
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT = 90  # 秒；建议关闭思考模式 ≥60，开启思考模式 ≥120


class PaperHubError(Exception):
    """PaperHub 调用异常，携带用户友好的错误消息。"""
    def __init__(self, message: str, *, user_hint: str = "", status_code: int = 0) -> None:
        super().__init__(message)
        self.user_hint = user_hint or message
        self.status_code = status_code


def _sanitize_error(exc_str: str) -> str:
    """脱敏异常字符串，避免 API Key / Bearer token 等机密外泄到用户提示/日志。

    覆盖 PaperHub / OpenAI SDK 常见泄漏来源：
      - Authorization 头（Bearer <token>）
      - URL query 参数 api_key=<value> / token=<value> / access_token=<value>
      - 孤立的 sk-... 风格 key（OpenAI 兼容）
    无匹配时原样返回。
    """
    if not exc_str:
        return exc_str
    patterns = [
        # Bearer <token> — 保留 4 位前缀示踪
        (re.compile(r"(Bearer\s+)([A-Za-z0-9_\-]{8,})", re.IGNORECASE),
         lambda m: f"{m.group(1)}{m.group(2)[:4]}***"),
        # api_key / token / access_token / apikey 查询参数
        (re.compile(r"((?:api[_-]?key|access[_-]?token|token)=)([A-Za-z0-9_\-]{8,})", re.IGNORECASE),
         lambda m: f"{m.group(1)}***"),
        # OpenAI 风格裸 key（sk-...）
        (re.compile(r"\b(sk-[A-Za-z0-9_\-]{4})[A-Za-z0-9_\-]{4,}\b"),
         lambda m: f"{m.group(1)}***"),
    ]
    result = exc_str
    for regex, repl in patterns:
        result = regex.sub(repl, result)
    return result


def _make_error_hint(exc_str: str, model: str, timeout: int) -> str:
    """将 API 异常分类为用户友好提示。"""
    # 先脱敏，保证任何分支回显 exc_str 时都不泄露机密
    exc_str = _sanitize_error(exc_str)
    s = exc_str.lower()
    if "401" in exc_str or "authentication" in s or "unauthorized" in s:
        return "API Key 无效或已过期，请检查设置中的 PaperHub API Key。"
    if "404" in exc_str or "model_not_found" in s or "does not exist" in s:
        return f"模型「{model}」不存在或不可用，建议在设置中刷新模型列表并重新选择。"
    if "timeout" in s or "timed out" in s:
        return (
            f"API 请求超时（{timeout}s）。"
            " 如已开启思考模式，建议关闭或将超时改为 120s 以上；"
            " 也可尝试缩短输入或切换模型。"
        )
    if "connection" in s or "network" in s or "refused" in s:
        return "网络连接失败，请检查网络是否能访问 PaperHub 服务。"
    if "rate_limit" in s or "429" in exc_str:
        return "API 请求频率超限，请稍后重试。"
    return f"PaperHub API 调用失败：{exc_str[:200]}"


def _call_paperhub_chat(
    api_key: str,
    base_url: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 1200,
    reasoning_enabled: bool = False,
    timeout: int = _DEFAULT_TIMEOUT,
    stream: bool = True,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> str:
    """
    调用 PaperHub Chat Completions 接口（系统+用户双消息），返回模型完整文本响应。

    参数：
      stream      True（默认）使用流式输出；on_chunk 每收到一个文本块时回调，
                  调用方可借此实时更新 UI。流式模式不受单次超时中断影响（超时
                  仅影响首 token 等待，后续增量传输独立计时）。
      on_chunk    仅在 stream=True 时有效；签名 (chunk_text: str) -> None。
      timeout     整体超时秒数；建议：关闭 reasoning ≥60s，开启 reasoning ≥120s。
    """
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise PaperHubError(
            "缺少 openai 包，请执行：pip install openai",
            user_hint="缺少依赖：请执行 pip install openai 安装 OpenAI SDK。",
        ) from exc

    if not api_key.strip():
        raise PaperHubError(
            "API Key 未填写",
            user_hint="未填写 PaperHub API Key，请在「设置 → PaperHub 设置」中配置。",
        )

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    create_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    if reasoning_enabled:
        create_kwargs["extra_body"] = {"reasoning": {"enabled": True}}

    try:
        if stream:
            create_kwargs["stream"] = True
            accumulated = ""
            resp_iter = client.chat.completions.create(**create_kwargs)
            # 墙钟超时守卫：OpenAI SDK 的 timeout 只管单次 HTTP 读写，
            # 流式接收时若服务端断断续续吐字会绕过该限制 → 这里再设一层总时长上限
            deadline = time.monotonic() + timeout
            for chunk in resp_iter:
                if time.monotonic() > deadline:
                    elapsed = timeout
                    raise PaperHubError(
                        f"流式响应超时（{elapsed}s）",
                        user_hint=f"流式响应超时（墙钟 {elapsed}s）。请在设置中调大 Timeout 或关闭流式输出。",
                    )
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                piece = getattr(delta, "content", None) or ""
                if piece:
                    accumulated += piece
                    if on_chunk is not None:
                        on_chunk(piece)
            return accumulated.strip()
        else:
            resp = client.chat.completions.create(**create_kwargs)
            content: Optional[str] = None
            if resp.choices:
                content = getattr(resp.choices[0].message, "content", None)
            return (content or "").strip()

    except Exception as exc:
        exc_str = str(exc)
        raise PaperHubError(
            exc_str,
            user_hint=_make_error_hint(exc_str, model, timeout),
        ) from exc


# ---------------------------------------------------------------------------
# 测试连接 & 模型列表
# ---------------------------------------------------------------------------

def test_paperhub_connection(
    api_key: str,
    base_url: str,
    model: str,
) -> Tuple[bool, str]:
    """向 PaperHub 发送最小请求验证 API Key 与连接是否有效。"""
    if not api_key.strip():
        return False, "API Key 不能为空，请先填写。"
    try:
        result = _call_paperhub_chat(
            api_key=api_key,
            base_url=base_url,
            model=model,
            system_prompt="你是一个测试助手。",
            user_prompt="请回复「OK」（仅用于连接测试）",
            temperature=0.1,
            max_tokens=16,
            reasoning_enabled=False,
            timeout=15,
        )
        if result:
            return True, f"连接成功！模型响应：{result[:80]}"
        return False, "模型返回为空，请检查模型名称是否正确。"
    except PaperHubError as exc:
        return False, exc.user_hint
    except Exception as exc:
        return False, f"连接失败：{exc}"


def fetch_paperhub_models(
    api_key: str,
    base_url: str,
) -> Tuple[bool, List[str], str]:
    """从 PaperHub 拉取可用模型列表。"""
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
# 翻译接口：三种策略
# ---------------------------------------------------------------------------

def _get_settings_params(settings: Dict[str, Any]) -> Dict[str, Any]:
    """从 settings 中提取 PaperHub 调用参数���"""
    return {
        "api_key": str(settings.get("paperhub_api_key") or "").strip(),
        "base_url": str(settings.get("paperhub_base_url") or "https://tc-paperhub.diezhi.net/v1"),
        "model": str(settings.get("paperhub_model") or "qwen3-max"),
        "reasoning": bool(settings.get("paperhub_reasoning_enabled", False)),
        "temperature": float(settings.get("paperhub_temperature", 0.7)),
        "max_tokens": int(settings.get("paperhub_max_tokens", 1200)),
        "timeout": max(10, int(settings.get("paperhub_timeout", _DEFAULT_TIMEOUT))),
        "stream": bool(settings.get("paperhub_stream", True)),
        "strategy": str(settings.get("paperhub_strategy") or "unmatched_only"),
        # 检索式注入开关 + 配额（默认开，可在 app_config.json 关闭回退到全量截断）
        "retrieval_enabled": bool(settings.get("prompt_retrieval_enabled", True)),
        "core_quota": max(0, int(settings.get("prompt_core_quota", 200))),
        "hit_quota": max(0, int(settings.get("prompt_hit_quota", 500))),
        "char_budget": max(500, int(settings.get("prompt_char_budget", 8000))),
    }


def _normalize_lexicon(bundle: Dict[str, Any]) -> Dict[str, str]:
    """规范化词库索引。"""
    lexicon = bundle.get("lexicon") or {}
    if not isinstance(lexicon, dict):
        lexicon = {}
    return {str(k): str(v) for k, v in lexicon.items() if str(k).strip()}


def _normalize_tts_map(bundle: Dict[str, Any]) -> Dict[str, str]:
    """规范化 TTS 映射。"""
    tts_map = bundle.get("tts_map") or {}
    if not isinstance(tts_map, dict):
        tts_map = {}
    return {str(k): str(v) for k, v in tts_map.items() if str(k).strip()}


def _apply_tts_map_to_conlang(conlang: str, tts_map: Dict[str, str]) -> str:
    """对自创语文本应用 TTS 映射，生成 TTS 音译。

    关键点：同一位置的字符最多被一条映射消费一次；替换产生的 spell 不会再次
    被后续映射扫描到，避免"链式误伤"（如 {a:b, b:c} 使 "a" 变成 "c"）。

    实现：从左到右扫描，每个位置用"当前剩余 tts_map 中最长的匹配"吞掉若干字符，
    吞掉的片段直接写入输出，不再参与后续匹配。
    """
    if not conlang or not tts_map:
        return conlang

    # 只考虑非空 key，按长度倒序以保证最长匹配优先
    items = sorted(
        ((w, s) for w, s in tts_map.items() if w),
        key=lambda kv: len(kv[0]),
        reverse=True,
    )
    if not items:
        return conlang

    out: list[str] = []
    i = 0
    n = len(conlang)
    while i < n:
        matched = False
        for word, spell in items:
            wlen = len(word)
            if wlen and conlang.startswith(word, i):
                out.append(spell)
                i += wlen
                matched = True
                break
        if not matched:
            out.append(conlang[i])
            i += 1
    return "".join(out)


def _fallback_tts(conlang: str, tts_map: Dict[str, str], ai_tts: str) -> str:
    """如果 AI 没提供 TTS，则用映射表推导。"""
    if ai_tts.strip():
        return ai_tts
    return _apply_tts_map_to_conlang(conlang, tts_map)


def translate_with_paperhub(
    settings: Dict[str, Any],
    bundle: Dict[str, Any],
    text: str,
    *,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> PaperHubResult:
    """
    PaperHub AI 翻译核心接口。

    根据策略（unmatched_only / always / confirm）执行翻译：
      - unmatched_only：先规则翻译 → 有未匹配词则 AI 补全 → 合并结果
      - always：直接 AI 翻译整句（AI 参考词库保持一致性）
      - confirm：AI 生成候选 → 返回结果供 UI 弹对话框确认

    返回 PaperHubResult，包含：
      conlang, tts, new_words, strategy_used, error, raw_response
    """
    text = text.strip()
    if not text:
        return PaperHubResult(error="输入文本为空。")

    params = _get_settings_params(settings)
    api_key = params["api_key"]

    if not api_key:
        return PaperHubResult(
            error="未填写 PaperHub API Key，请在「设置 → PaperHub 设置」中配置。",
            strategy_used=params["strategy"],
        )

    lexicon = _normalize_lexicon(bundle)
    tts_map = _normalize_tts_map(bundle)
    strategy = params["strategy"]
    system_prompt = _build_system_prompt(
        bundle,
        input_text=text,
        retrieval_enabled=params["retrieval_enabled"],
        core_quota=params["core_quota"],
        hit_quota=params["hit_quota"],
        char_budget=params["char_budget"],
    )

    # 公共调用参数
    _common = dict(
        api_key=api_key,
        base_url=params["base_url"],
        model=params["model"],
        system_prompt=system_prompt,
        temperature=params["temperature"],
        max_tokens=params["max_tokens"],
        reasoning_enabled=params["reasoning"],
        timeout=params["timeout"],
        stream=params["stream"],
        on_chunk=on_chunk,
    )

    # ── always 策略：直接 AI 翻译 ───────────────────────────────────
    if strategy == "always":
        user_prompt = _build_user_prompt_full(text)
        try:
            raw = _call_paperhub_chat(user_prompt=user_prompt, **_common)
        except PaperHubError as exc:
            rule_result = translate_multiline_rule(text, lexicon, tts_map)
            return PaperHubResult(
                conlang=rule_result.conlang,
                tts=rule_result.phonetic,
                strategy_used="always→rule_fallback",
                error=exc.user_hint,
            )

        parsed = _parse_paperhub_response(raw)
        parsed.strategy_used = "always"
        parsed.tts = _fallback_tts(parsed.conlang, tts_map, parsed.tts)
        if parsed.error and not parsed.conlang:
            rule_result = translate_multiline_rule(text, lexicon, tts_map)
            parsed.conlang = rule_result.conlang
            parsed.tts = rule_result.phonetic
            parsed.strategy_used = "always→rule_fallback"
        return parsed

    # ── unmatched_only 策略：规则 + AI 补全 ──────────────────────────
    if strategy == "unmatched_only":
        rule_result = translate_multiline_rule(text, lexicon, tts_map)
        unmatched = rule_result.unmatched_words

        if not unmatched:
            return PaperHubResult(
                conlang=rule_result.conlang,
                tts=rule_result.phonetic,
                strategy_used="unmatched_only→rule_only",
            )

        rule_conlang_clean = re.sub(r"【.*?】", "[未匹配]", rule_result.conlang)
        user_prompt = _build_user_prompt_unmatched(text, unmatched, rule_conlang_clean)
        try:
            raw = _call_paperhub_chat(user_prompt=user_prompt, **_common)
        except PaperHubError as exc:
            return PaperHubResult(
                conlang=rule_result.conlang,
                tts=rule_result.phonetic,
                strategy_used="unmatched_only→rule_fallback",
                error=exc.user_hint,
            )

        parsed = _parse_paperhub_response(raw)
        parsed.strategy_used = "unmatched_only"
        parsed.tts = _fallback_tts(parsed.conlang, tts_map, parsed.tts)

        if parsed.error and not parsed.conlang:
            parsed.conlang = rule_result.conlang
            parsed.tts = rule_result.phonetic
            parsed.strategy_used = "unmatched_only→rule_fallback"

        return parsed

    # ── confirm 策略：AI 生成候选，交由 UI 确认 ──────────────────────
    if strategy == "confirm":
        user_prompt = _build_user_prompt_full(text)
        try:
            raw = _call_paperhub_chat(user_prompt=user_prompt, **_common)
        except PaperHubError as exc:
            rule_result = translate_multiline_rule(text, lexicon, tts_map)
            return PaperHubResult(
                conlang=rule_result.conlang,
                tts=rule_result.phonetic,
                strategy_used="confirm→rule_fallback",
                error=exc.user_hint,
            )

        parsed = _parse_paperhub_response(raw)
        parsed.strategy_used = "confirm"
        parsed.tts = _fallback_tts(parsed.conlang, tts_map, parsed.tts)

        if parsed.error and not parsed.conlang:
            rule_result = translate_multiline_rule(text, lexicon, tts_map)
            parsed.conlang = rule_result.conlang
            parsed.tts = rule_result.phonetic
            parsed.strategy_used = "confirm→rule_fallback"

        return parsed

    # 未知策略
    return PaperHubResult(
        error=f"未知的翻译策略：{strategy}",
        strategy_used=strategy,
    )


# ---------------------------------------------------------------------------
# 兼容旧接口（translate_multiline_paperhub）
# ---------------------------------------------------------------------------

def translate_multiline_paperhub(
    settings: Dict[str, Any],
    bundle: Dict[str, Any],
    text: str,
) -> Tuple[str, str, str]:
    """
    兼容旧调用方式的接口：返回 (conlang, tts, tail) 三元组。
    tail 为错误信息或空字符串。
    """
    result = translate_with_paperhub(settings, bundle, text)
    tail = result.error
    return result.conlang, result.tts, tail