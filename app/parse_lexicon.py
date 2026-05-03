from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# 词性（POS）拆分
# ---------------------------------------------------------------------------

# 匹配词条中的词性标注括号 (.xxx/yyy) 或 (.xxx)
_POS_BRACKET_RE = re.compile(r"\(\.[a-zA-Z]+/[\u4e00-\u9fff\w]*\)")
_POS_SHORT_RE = re.compile(r"\(\.[a-zA-Z]+\)")


def split_pos_from_key(raw_key: str) -> Tuple[str, str]:
    """从词库 key 中剥离词性括号，返回 (纯中文词, 词性标注)。

    示例：
      "那个(.n/指示代词)" → ("那个", ".n/指示代词")
      "跑(.v)" → ("跑", ".v")
      "水" → ("水", "")
    """
    key = raw_key.strip()
    if not key:
        return ("", "")
    # 先尝试完整格式 (.xxx/yyy)
    m = _POS_BRACKET_RE.search(key)
    if m:
        pos = m.group()[1:-1]  # 剥掉外层括号 → ".n/指示代词"
        cn = key[:m.start()] + key[m.end():]
        return (cn.strip(), pos)
    # 再尝试短格式 (.xxx)
    m = _POS_SHORT_RE.search(key)
    if m:
        pos = m.group()[1:-1]  # → ".v"
        cn = key[:m.start()] + key[m.end():]
        return (cn.strip(), pos)
    return (key, "")


@dataclass
class PosEntry:
    """一个中文词的单个义项，含词性标注。"""
    cn: str          # 纯中文词（不含括号）
    pos: str         # 词性标注，如 ".n/指示代词" 或 ".v"；无标注时为空字符串
    conlang: str     # 自创语翻译


ZH_KEYS = frozenset(
    {
        "zh",
        "cn",
        "chinese",
        "中文",
        "source",
        "src",
        "han",
        "hanzi",
        "原文",
        "汉语",
    }
)
CON_KEYS = frozenset(
    {
        "conlang",
        "target",
        "tl",
        "translation",
        "译",
        "译本",
        "译词",
        "词",
        "词条",
        "自创语",
        "目标语",
    }
)


def _is_cjk_heavy(s: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in s)


def _pick_zh_con_pair(obj: Dict[str, Any]) -> Tuple[str | None, str | None]:
    zh_val: str | None = None
    con_val: str | None = None
    lower_map = {str(k).lower(): (k, v) for k, v in obj.items() if isinstance(k, str)}
    for zk in ZH_KEYS:
        hit = lower_map.get(zk.lower())
        if hit and isinstance(hit[1], str) and hit[1].strip():
            zh_val = hit[1].strip()
            break
    for ck in CON_KEYS:
        hit = lower_map.get(ck.lower())
        if hit and isinstance(hit[1], str) and hit[1].strip():
            con_val = hit[1].strip()
            break
    if zh_val and con_val:
        return zh_val, con_val

    str_vals = [(str(k), str(v)) for k, v in obj.items() if isinstance(k, str) and isinstance(v, str)]
    cjk_keys = [(k, v) for k, v in str_vals if _is_cjk_heavy(k) and v.strip()]
    if len(cjk_keys) == 1:
        k, v = cjk_keys[0]
        return k.strip(), v.strip()

    return zh_val, con_val


def _walk_collect(obj: Any, acc: Dict[str, str]) -> None:
    if isinstance(obj, list):
        for item in obj:
            _walk_collect(item, acc)
        return
    if not isinstance(obj, dict):
        return

    zh, con = _pick_zh_con_pair(obj)
    if zh and con:
        # 剥离词性括号，纯中文词作为 key
        cn, pos = split_pos_from_key(zh)
        if cn:
            acc.setdefault(cn, con)

    for v in obj.values():
        if isinstance(v, (dict, list)):
            _walk_collect(v, acc)

    for list_key in ("entries", "words", "items", "lexicon", "dictionary", "vocabulary"):
        child = obj.get(list_key)
        if isinstance(child, list):
            for item in child:
                _walk_collect(item, acc)


def build_lexicon_index(data: Any) -> Dict[str, str]:
    """构建词库索引（纯中文词 → 自创语翻译）。

    自动剥离 key 中的词性括号 (.xxx/yyy)，确保匹配时使用纯中文词。
    同词多义项时，取第一个出现的翻译（后续义项由 build_lexicon_index_with_pos 处理）。
    """
    acc: Dict[str, str] = {}
    if isinstance(data, dict):
        if all(isinstance(v, str) for v in data.values()) and all(isinstance(k, str) for k in data.keys()):
            cjk = sum(1 for k in data if _is_cjk_heavy(k))
            if cjk > 0 and cjk >= max(1, len(data) // 4):
                for k, v in data.items():
                    if _is_cjk_heavy(k) and v.strip():
                        cn, pos = split_pos_from_key(k.strip())
                        if cn:
                            acc.setdefault(cn, v.strip())
                return acc

    if isinstance(data, dict) and all(isinstance(v, str) for v in data.values()):
        for k, v in data.items():
            if isinstance(k, str) and _is_cjk_heavy(k) and v.strip():
                cn, pos = split_pos_from_key(k.strip())
                if cn:
                    acc.setdefault(cn, v.strip())
        if acc:
            return acc

    _walk_collect(data, acc)
    return acc


def build_lexicon_index_with_pos(data: Any) -> Dict[str, List[PosEntry]]:
    """构建带词性的词库索引（纯中文词 → 多义项列表）。

    同词不同词性时，多个 PosEntry 共存于同一 key 下。
    用于 rule_translator 的两级匹配策略。
    """
    acc: Dict[str, List[PosEntry]] = {}

    if isinstance(data, dict):
        # 平铺字典格式（Conlang_Master_Library.json 的常见格式）
        if all(isinstance(v, str) for v in data.values()) and all(isinstance(k, str) for k in data.keys()):
            cjk = sum(1 for k in data if _is_cjk_heavy(k))
            if cjk > 0 and cjk >= max(1, len(data) // 4):
                for k, v in data.items():
                    if _is_cjk_heavy(k) and v.strip():
                        cn, pos = split_pos_from_key(k.strip())
                        if cn:
                            acc.setdefault(cn, []).append(PosEntry(cn=cn, pos=pos, conlang=v.strip()))
                return acc

        if all(isinstance(v, str) for v in data.values()):
            for k, v in data.items():
                if isinstance(k, str) and _is_cjk_heavy(k) and v.strip():
                    cn, pos = split_pos_from_key(k.strip())
                    if cn:
                        acc.setdefault(cn, []).append(PosEntry(cn=cn, pos=pos, conlang=v.strip()))
            if acc:
                return acc

    # 复杂嵌套结构：使用 _walk_collect_with_pos
    _walk_collect_with_pos(data, acc)
    return acc


def _walk_collect_with_pos(obj: Any, acc: Dict[str, List[PosEntry]]) -> None:
    """遍历复杂结构，收集带词性的词条。"""
    if isinstance(obj, list):
        for item in obj:
            _walk_collect_with_pos(item, acc)
        return
    if not isinstance(obj, dict):
        return

    zh, con = _pick_zh_con_pair(obj)
    if zh and con:
        cn, pos = split_pos_from_key(zh)
        if cn:
            acc.setdefault(cn, []).append(PosEntry(cn=cn, pos=pos, conlang=con))

    for v in obj.values():
        if isinstance(v, (dict, list)):
            _walk_collect_with_pos(v, acc)

    for list_key in ("entries", "words", "items", "lexicon", "dictionary", "vocabulary"):
        child = obj.get(list_key)
        if isinstance(child, list):
            for item in child:
                _walk_collect_with_pos(item, acc)


def load_master_library(path: Path) -> Tuple[Dict[str, str], Dict[str, List[PosEntry]], int, Any]:
    """加载主词库文件，返回两个索引 + 词条数 + 原始数据。

    返回值：
      index      — Dict[str, str]，纯中文词 → 自创语翻译（兼容旧接口）
      pos_index  — Dict[str, List[PosEntry]]，纯中文词 → 多义项列表（含词性）
      count      — 词条总数
      raw_data   — JSON 原始数据
    """
    raw_text = path.read_text(encoding="utf-8")
    data = json.loads(raw_text)
    index = build_lexicon_index(data)
    pos_index = build_lexicon_index_with_pos(data)
    return index, pos_index, len(index), data
