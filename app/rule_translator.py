"""
规则模式翻译引擎 — 三级转换流水线

第一级：中文 → 自创语（词库最长匹配，未命中用【】标记）
第二级：自创语 → TTS 友好音译（Mapping_Rules.csv 映射）
第三级：构造可写入 Translation_History.json 的结构化结果

情绪检测（EmotionResult / detect_emotion）为存根接口，
预留给后续 TTS 批量语音生成阶段使用。
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 标点集合
# ---------------------------------------------------------------------------

CLAUSE_PUNCT: frozenset[str] = frozenset("。！？，、!?,.")

_PUNCT_PASSTHROUGH: Dict[str, str] = {
    "。": "。",
    "！": "！",
    "？": "？",
    "，": "，",
    "、": "、",
    "!": "!",
    "?": "?",
    ".": ".",
    ",": ",",
}

# ---------------------------------------------------------------------------
# 情绪检测（存根 —— 供后续 TTS 批量生成阶段扩展）
# ---------------------------------------------------------------------------

_EMOTION_KEYWORDS: Dict[str, List[str]] = {
    "positive": ["高兴", "快乐", "开心", "喜悦", "幸福", "爱", "美好", "感谢", "棒", "好"],
    "negative": ["难过", "悲伤", "痛苦", "生气", "愤怒", "恨", "害怕", "担心", "哭", "坏"],
    "surprised": ["惊讶", "没想到", "居然", "竟然", "不可思议"],
    "question": ["吗", "呢", "为什么", "怎么", "哪", "谁", "什么", "几"],
}

_TTS_HINTS: Dict[str, Tuple[str, str]] = {
    "positive": ("high", "normal"),
    "negative": ("low", "slow"),
    "surprised": ("high", "fast"),
    "question": ("rising", "normal"),
    "neutral": ("normal", "normal"),
}

EMOTION_DISPLAY_NAMES: Dict[str, str] = {
    "positive": "积极",
    "negative": "消极",
    "surprised": "惊讶",
    "question": "疑问",
    "neutral": "中性",
}


@dataclass
class EmotionResult:
    """
    情绪检测结果。

    当前为关键字规则匹配；`tts_pitch_hint` / `tts_rate_hint` 预留给
    后续 TTS 批量语音生成阶段，用于调节合成语调与语速。
    """

    label: str = "neutral"
    intensity: float = 0.5
    keywords_found: List[str] = field(default_factory=list)
    tts_pitch_hint: str = "normal"
    tts_rate_hint: str = "normal"

    @property
    def display_name(self) -> str:
        return EMOTION_DISPLAY_NAMES.get(self.label, self.label)


def detect_emotion(text: str) -> EmotionResult:
    """
    基于关键字的轻量情绪检测。

    预留扩展接口：后续可将此函数替换为调用 NLP 模型的实现，
    只要返回 EmotionResult 即可兼容现有流水线。
    """
    found: Dict[str, List[str]] = {}
    for label, keywords in _EMOTION_KEYWORDS.items():
        hits = [kw for kw in keywords if kw in text]
        if hits:
            found[label] = hits

    if not found:
        pitch, rate = _TTS_HINTS["neutral"]
        return EmotionResult("neutral", 0.5, [], pitch, rate)

    best_label = max(found, key=lambda k: len(found[k]))
    all_kws = [kw for kws in found.values() for kw in kws]
    intensity = min(1.0, len(all_kws) / 5.0)
    pitch, rate = _TTS_HINTS.get(best_label, ("normal", "normal"))
    return EmotionResult(best_label, intensity, all_kws, pitch, rate)


# ---------------------------------------------------------------------------
# 分词与翻译数据结构
# ---------------------------------------------------------------------------


@dataclass
class TokenResult:
    """单个分词后的翻译结果。"""

    source: str
    conlang: str
    is_matched: bool
    is_punct: bool = False


@dataclass
class SentenceResult:
    """单个子句的翻译结果。"""

    source: str
    conlang: str
    phonetic: str
    tokens: List[TokenResult]
    unmatched_words: List[str]
    match_count: int
    total_tokens: int


@dataclass
class RuleTranslationResult:
    """完整翻译结果，供界面展示与历史写入使用。"""

    source: str
    conlang: str
    phonetic: str
    unmatched_words: List[str]
    match_count: int
    total_tokens: int
    elapsed_ms: float
    emotion: EmotionResult
    sentences: List[SentenceResult] = field(default_factory=list)

    @property
    def match_rate(self) -> float:
        if self.total_tokens == 0:
            return 1.0
        return self.match_count / self.total_tokens


# ---------------------------------------------------------------------------
# 第一级核心：中文 → 自创语
# ---------------------------------------------------------------------------


def _split_into_clauses(text: str) -> List[Tuple[str, str]]:
    """
    将文本按标点分割为 (子句文本, 跟随标点) 的列表。
    连续标点会追加到前一个子句的标点字段。
    """
    segments: List[Tuple[str, str]] = []
    current: str = ""
    for ch in text:
        if ch in CLAUSE_PUNCT:
            if current.strip():
                segments.append((current.strip(), ch))
                current = ""
            elif segments:
                prev_text, prev_punct = segments[-1]
                segments[-1] = (prev_text, prev_punct + ch)
        else:
            current += ch
    if current.strip():
        segments.append((current.strip(), ""))
    return segments


def _segment_longest_match(
    text: str,
    lexicon: Dict[str, str],
) -> List[TokenResult]:
    """词库最长匹配分词。未命中字符用【】标记，连续未命中合并为一个 token。"""
    keys = sorted((k for k in lexicon if k), key=len, reverse=True)
    tokens: List[TokenResult] = []
    i = 0
    n = len(text)
    while i < n:
        matched = False
        for k in keys:
            if text.startswith(k, i):
                tokens.append(TokenResult(k, lexicon[k], True))
                i += len(k)
                matched = True
                break
        if not matched:
            ch = text[i]
            if ch in CLAUSE_PUNCT:
                punct_out = _PUNCT_PASSTHROUGH.get(ch, ch)
                tokens.append(TokenResult(ch, punct_out, True, True))
            elif tokens and not tokens[-1].is_matched and not tokens[-1].is_punct:
                prev = tokens[-1]
                merged_src = prev.source + ch
                tokens[-1] = TokenResult(merged_src, f"【{merged_src}】", False)
            else:
                tokens.append(TokenResult(ch, f"【{ch}】", False))
            i += 1
    return tokens


def _build_conlang_from_tokens(tokens: List[TokenResult]) -> str:
    """词间加空格；标点直接附着在前一词后（无前置空格），标点后加空格。"""
    if not tokens:
        return ""
    parts: List[str] = []
    for i, tok in enumerate(tokens):
        parts.append(tok.conlang)
        if i < len(tokens) - 1:
            next_tok = tokens[i + 1]
            # 下一个 token 不是标点 → 加空格（标点直接附着到词上不加前置空格）
            if not next_tok.is_punct:
                parts.append(" ")
    return "".join(parts)


# ---------------------------------------------------------------------------
# 第二级：自创语 → TTS 友好音译
# ---------------------------------------------------------------------------


def _build_tts_from_tokens(
    tokens: List[TokenResult],
    tts_map: Dict[str, str],
) -> str:
    """
    逐 token 构建 TTS 输出：
    - 已匹配的自创语词 → 查 tts_map，找到则用 TTS 拼写，找不到保留自创语词原样。
    - 未匹配的中文字词 → 保留【中文】标记（Level 1 未命中传递）。
    - 标点 → 直接透传。
    """
    parts: List[str] = []
    for i, tok in enumerate(tokens):
        if tok.is_punct:
            parts.append(tok.conlang)
        elif tok.is_matched:
            parts.append(tts_map.get(tok.conlang, tok.conlang))
        else:
            parts.append(f"【{tok.source}】")
        if i < len(tokens) - 1 and not tokens[i + 1].is_punct:
            parts.append(" ")
    return "".join(parts)


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def translate_rule(
    source: str,
    lexicon: Dict[str, str],
    tts_map: Dict[str, str],
) -> RuleTranslationResult:
    """
    规则模式单段翻译（支持含标点的多子句文本）。

    三级流水线：
      1. 中文 → 自创语（词库最长匹配，未命中标 【】）
      2. 自创语 → TTS 友好音译（Mapping_Rules.csv 查表）
      3. 构造含情绪信息的 RuleTranslationResult
    """
    t0 = time.monotonic()
    source = re.sub(r"[ \t]+", " ", source).strip()
    emotion = detect_emotion(source)

    clause_pairs = _split_into_clauses(source)
    if not clause_pairs:
        clause_pairs = [(source, "")]

    sentences: List[SentenceResult] = []
    conlang_parts: List[str] = []
    phonetic_parts: List[str] = []
    all_unmatched: List[str] = []
    total_match = 0
    total_tokens = 0

    for clause_text, punct in clause_pairs:
        if not clause_text:
            continue
        tokens = _segment_longest_match(clause_text, lexicon)

        conlang_clause = _build_conlang_from_tokens(tokens) + punct
        phonetic_clause = _build_tts_from_tokens(tokens, tts_map) + _PUNCT_PASSTHROUGH.get(
            punct, punct
        ) if punct else _build_tts_from_tokens(tokens, tts_map)

        unmatched_clause: List[str] = []
        matched_count = 0
        real_token_count = 0
        for tok in tokens:
            if tok.is_punct:
                continue
            real_token_count += 1
            if tok.is_matched:
                matched_count += 1
            else:
                raw = tok.source.strip()
                if raw and raw not in unmatched_clause:
                    unmatched_clause.append(raw)

        sentences.append(
            SentenceResult(
                source=clause_text + punct,
                conlang=conlang_clause,
                phonetic=phonetic_clause,
                tokens=tokens,
                unmatched_words=unmatched_clause,
                match_count=matched_count,
                total_tokens=real_token_count,
            )
        )
        conlang_parts.append(conlang_clause)
        phonetic_parts.append(phonetic_clause)
        for u in unmatched_clause:
            if u not in all_unmatched:
                all_unmatched.append(u)
        total_match += matched_count
        total_tokens += real_token_count

    elapsed = (time.monotonic() - t0) * 1000

    return RuleTranslationResult(
        source=source,
        conlang=" ".join(p for p in conlang_parts if p),
        phonetic=" ".join(p for p in phonetic_parts if p),
        unmatched_words=all_unmatched,
        match_count=total_match,
        total_tokens=total_tokens,
        elapsed_ms=elapsed,
        emotion=emotion,
        sentences=sentences,
    )


def translate_multiline_rule(
    text: str,
    lexicon: Dict[str, str],
    tts_map: Dict[str, str],
) -> RuleTranslationResult:
    """
    多行输入的规则翻译：逐非空行调用 translate_rule，聚合结果。
    空行在输出中保留为空行，以维持原始排版。
    """
    t0 = time.monotonic()
    lines = text.splitlines()
    all_conlang: List[str] = []
    all_phonetic: List[str] = []
    all_unmatched: List[str] = []
    all_sentences: List[SentenceResult] = []
    total_match = 0
    total_tokens = 0

    full_emotion = detect_emotion(text)

    for line in lines:
        if not line.strip():
            all_conlang.append("")
            all_phonetic.append("")
            continue
        res = translate_rule(line, lexicon, tts_map)
        all_conlang.append(res.conlang)
        all_phonetic.append(res.phonetic)
        all_sentences.extend(res.sentences)
        for u in res.unmatched_words:
            if u not in all_unmatched:
                all_unmatched.append(u)
        total_match += res.match_count
        total_tokens += res.total_tokens

    elapsed = (time.monotonic() - t0) * 1000
    return RuleTranslationResult(
        source=text,
        conlang="\n".join(all_conlang),
        phonetic="\n".join(all_phonetic),
        unmatched_words=all_unmatched,
        match_count=total_match,
        total_tokens=total_tokens,
        elapsed_ms=elapsed,
        emotion=full_emotion,
        sentences=all_sentences,
    )
