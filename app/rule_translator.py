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

from app.parse_lexicon import PosEntry

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
    is_space: bool = False  # 用户手动输入的空格（词组断词边界）


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
    *,
    respect_spaces: bool = False,
    pos_lexicon: Optional[Dict[str, List[PosEntry]]] = None,
) -> List[TokenResult]:
    """
    词库最长匹配分词。未命中字符用【】标记，连续未命中合并为一个 token。

    respect_spaces=True 时，源文本中的空格被视为用户手动断词边界：
      - 空格本身产生 is_space=True 的 token，用于在输出中保留词组间距；
      - 最长匹配不会跨越空格边界（空格两侧各自独立匹配）。
    """
    keys = sorted((k for k in lexicon if k), key=len, reverse=True)
    # 按空格切分文本，分别独立匹配每个片段
    if respect_spaces:
        fragments = text.split(" ")
        tokens: List[TokenResult] = []
        for idx, frag in enumerate(fragments):
            if frag:
                frag_tokens = _segment_longest_match(
                    frag, lexicon, respect_spaces=False, pos_lexicon=pos_lexicon,
                )
                tokens.extend(frag_tokens)
            # 在片段之间插入空格边界 token（末尾片段后不加）
            if idx < len(fragments) - 1:
                tokens.append(TokenResult(" ", " ", False, False, True))
        return tokens

    # 常规模式：整个文本做最长匹配
    tokens: List[TokenResult] = []
    i = 0
    n = len(text)
    while i < n:
        matched = False
        for k in keys:
            if text.startswith(k, i):
                # 当有词性词库时，优先用两级匹配策略获取翻译
                if pos_lexicon and k in pos_lexicon:
                    con_val = _resolve_pos_match(k, pos_lexicon)
                else:
                    con_val = lexicon[k]
                tokens.append(TokenResult(k, con_val, True))
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


def _resolve_pos_match(
    cn_word: str,
    pos_lexicon: Dict[str, List[PosEntry]],
    jieba_pos_hint: str = "",
) -> str:
    """两级词性匹配策略：

    1. 精确匹配：cn_word + jieba 词性 → 找到同 pos 的义项
    2. 宽松 fallback：仅用 cn_word → 取第一个义项

    返回匹配到的自创语翻译；找不到时返回空字符串。
    """
    entries = pos_lexicon.get(cn_word)
    if not entries:
        return ""

    # 如果 jieba 提供了词性提示，尝试精确匹配
    if jieba_pos_hint:
        # jieba 词性格式如 "v" / "n" / "r" 等
        # 词库 pos 格式如 ".v/动词" / ".n/名词" / ".n"
        # 精确匹配逻辑：jieba_pos_hint 匹配 pos 中 "." 后的第一个字母
        for entry in entries:
            if entry.pos:
                pos_letter = entry.pos.lstrip(".").split("/")[0].strip()
                if pos_letter == jieba_pos_hint:
                    return entry.conlang

    # fallback：取第一个义项（无 pos 或 pos 不匹配时）
    return entries[0].conlang


def _build_conlang_from_tokens(tokens: List[TokenResult]) -> str:
    """
    词间加空格；标点直接附着在前一词后（无前置空格），标点后加空格；
    用户空格边界 token（is_space）在输出中产生空格分隔词组。
    """
    if not tokens:
        return ""
    parts: List[str] = []
    for i, tok in enumerate(tokens):
        if tok.is_space:
            # 用户空格边界：直接输出空格
            parts.append(" ")
            continue
        parts.append(tok.conlang)
        if i < len(tokens) - 1:
            next_tok = tokens[i + 1]
            # 下一个 token 不是标点也不是用户空格 → 加空格
            if not next_tok.is_punct and not next_tok.is_space:
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
    - 用户空格边界 → 输出空格（词组断词）。
    """
    parts: List[str] = []
    for i, tok in enumerate(tokens):
        if tok.is_space:
            parts.append(" ")
            continue
        if tok.is_punct:
            parts.append(tok.conlang)
        elif tok.is_matched:
            parts.append(tts_map.get(tok.conlang, tok.conlang))
        else:
            parts.append(f"【{tok.source}】")
        if i < len(tokens) - 1 and not tokens[i + 1].is_punct and not tokens[i + 1].is_space:
            parts.append(" ")
    return "".join(parts)


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def _has_user_spaces(text: str) -> bool:
    """检测文本中是否含有用户手动输入的空格（中文之间或词间的空格）。
    如果原始文本在去掉首尾空白后内部仍有空格，视为用户有意断词。
    """
    stripped = text.strip()
    # 检查内部是否有空格（排除仅由空格组成的文本）
    inner = stripped.replace("\n", "")
    return " " in inner


def translate_rule(
    source: str,
    lexicon: Dict[str, str],
    tts_map: Dict[str, str],
    pos_lexicon: Optional[Dict[str, List[PosEntry]]] = None,
) -> RuleTranslationResult:
    """
    规则模式单段翻译（支持含标点的多子句文本）。

    三级流水线：
      1. 中文 → 自创语（词库最长匹配，未命中标 【】）
      2. 自创语 → TTS 友好音译（Mapping_Rules.csv 查表）
      3. 构造含情绪信息的 RuleTranslationResult

    用户空格处理：
      - 输入中的空格被视为用户手动断词/断句边界
      - 空格两侧的词组各自独立匹配词库
      - 输出中保留用户空格作为词组间距
    """
    t0 = time.monotonic()
    # 保留用户空格（不再 strip 后丢失内部空格信息）
    original = source
    source = re.sub(r"[ \t]+", " ", source).strip()
    emotion = detect_emotion(source)

    # 检测用户是否手动输入了空格（断词边界）
    respect_spaces = _has_user_spaces(original)

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
        tokens = _segment_longest_match(clause_text, lexicon, respect_spaces=respect_spaces, pos_lexicon=pos_lexicon)

        conlang_clause = _build_conlang_from_tokens(tokens) + punct
        phonetic_clause = _build_tts_from_tokens(tokens, tts_map) + _PUNCT_PASSTHROUGH.get(
            punct, punct
        ) if punct else _build_tts_from_tokens(tokens, tts_map)

        unmatched_clause: List[str] = []
        matched_count = 0
        real_token_count = 0
        for tok in tokens:
            if tok.is_punct or tok.is_space:
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
    pos_lexicon: Optional[Dict[str, List[PosEntry]]] = None,
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
        res = translate_rule(line, lexicon, tts_map, pos_lexicon)
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
