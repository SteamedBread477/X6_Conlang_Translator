"""
IPA 国际音标生成模块。

规则模式：从 Mapping_Rules.csv 的「IPA音标」列查表，按词拼接。
- 已知词：直接返回对应 IPA
- 未知词：标注为 [word?]
- 【未匹配汉语】标记：原样保留

公开接口：
    generate_ipa_rule(conlang_text, ipa_map) -> (ipa_str, missing_words)
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple


# 附着在词上的标点字符（剥离后查表）
_PUNCT = r""".,!?;:()[]{}「」『』""''—–…"""


def _strip_punct(token: str) -> Tuple[str, str, str]:
    """剥离 token 前后的标点，返回 (prefix, core, suffix)。"""
    m_pre = re.match(rf"^([{re.escape(_PUNCT)}]*)", token)
    prefix = m_pre.group(1) if m_pre else ""
    rest = token[len(prefix):]
    m_suf = re.search(rf"([{re.escape(_PUNCT)}]*)$", rest)
    suffix = m_suf.group(1) if m_suf and m_suf.group(1) else ""
    core = rest[: len(rest) - len(suffix)] if suffix else rest
    return prefix, core, suffix


def generate_ipa_rule(
    conlang_text: str,
    ipa_map: Dict[str, str],
) -> Tuple[str, List[str]]:
    """
    将自创语文本按词查找 IPA，拼接为完整 IPA 字符串。

    返回：
        ipa_str      - 格式为 /词1 词2 .../ 的字符串；
                       未知词用 [word?] 占位；
                       【汉字】标记原样保留（表示词库未覆盖）
        missing_words - 未在 ipa_map 中找到的纯词列表
    """
    if not conlang_text.strip() or not ipa_map:
        return "", []

    # 小写键映射，支持大小写不敏感查找
    lower_map: Dict[str, str] = {k.strip().lower(): v.strip() for k, v in ipa_map.items() if k.strip()}

    parts: List[str] = []
    missing: List[str] = []

    # 按空白切分，保留各 token
    for raw_token in conlang_text.strip().split():
        raw_token = raw_token.strip()
        if not raw_token:
            continue

        # 【...】：词库未匹配的汉语原文，原样保留
        if raw_token.startswith("【") and raw_token.endswith("】"):
            parts.append(raw_token)
            continue

        prefix, core, suffix = _strip_punct(raw_token)

        if not core:
            parts.append(raw_token)
            continue

        lookup = core.lower()
        if lookup in lower_map:
            parts.append(prefix + lower_map[lookup] + suffix)
        else:
            # 尝试去掉末尾变格词缀后再查（简单回退：截去最后1~2个字母）
            found = False
            for trim in (1, 2):
                if len(lookup) > trim + 2 and lookup[:-trim] in lower_map:
                    parts.append(prefix + lower_map[lookup[:-trim]] + f"({suffix or ''}…)")
                    found = True
                    break
            if not found:
                parts.append(prefix + f"[{core}?]" + suffix)
                missing.append(core)

    if not parts:
        return "", missing

    ipa_text = " ".join(parts)

    # 只有全是未知词 / 汉字标记时不加斜杠包裹
    has_real_ipa = any(
        not (t.startswith("[") and t.endswith("?]")) and not t.startswith("【")
        for t in parts
    )
    result = f"/{ipa_text}/" if has_real_ipa else ipa_text
    return result, missing
