from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

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
        acc.setdefault(zh, con)

    for v in obj.values():
        if isinstance(v, (dict, list)):
            _walk_collect(v, acc)

    for list_key in ("entries", "words", "items", "lexicon", "dictionary", "vocabulary"):
        child = obj.get(list_key)
        if isinstance(child, list):
            for item in child:
                _walk_collect(item, acc)


def build_lexicon_index(data: Any) -> Dict[str, str]:
    acc: Dict[str, str] = {}
    if isinstance(data, dict):
        if all(isinstance(v, str) for v in data.values()) and all(isinstance(k, str) for k in data.keys()):
            cjk = sum(1 for k in data if _is_cjk_heavy(k))
            if cjk > 0 and cjk >= max(1, len(data) // 4):
                for k, v in data.items():
                    if _is_cjk_heavy(k) and v.strip():
                        acc[k.strip()] = v.strip()
                return acc

    if isinstance(data, dict) and all(isinstance(v, str) for v in data.values()):
        for k, v in data.items():
            if isinstance(k, str) and _is_cjk_heavy(k) and v.strip():
                acc[k.strip()] = v.strip()
        if acc:
            return acc

    _walk_collect(data, acc)
    return acc


def load_master_library(path: Path) -> Tuple[Dict[str, str], int, Any]:
    raw_text = path.read_text(encoding="utf-8")
    data = json.loads(raw_text)
    index = build_lexicon_index(data)
    return index, len(index), data
