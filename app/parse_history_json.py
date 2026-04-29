from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple

from app.parse_lexicon import _is_cjk_heavy


def _norm_anchor_key(s: str) -> str:
    return " ".join((s or "").strip().split())


def _pair_from_mapping_like(obj: Dict[str, Any]) -> Dict[str, str]:
    anchors: Dict[str, str] = {}
    for k, v in obj.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        if not v.strip():
            continue
        if _is_cjk_heavy(k) or any("\u4e00" <= c <= "\u9fff" for c in k):
            anchors[_norm_anchor_key(k)] = v.strip()
    return anchors


def _from_list_records(data: list) -> Dict[str, str]:
    anchors: Dict[str, str] = {}
    zh_keys = frozenset(
        {"zh", "cn", "chinese", "中文", "source", "原文", "汉语", "hanzi"}
    )
    con_keys = frozenset(
        {"conlang", "target", "translation", "译", "译本", "自创语", "结果"}
    )
    for item in data:
        if not isinstance(item, dict):
            continue
        zh: str | None = None
        con: str | None = None
        lower = {str(k).lower(): v for k, v in item.items()}
        for zk in zh_keys:
            v = lower.get(zk.lower())
            if isinstance(v, str) and v.strip():
                zh = v.strip()
                break
        for ck in con_keys:
            v = lower.get(ck.lower())
            if isinstance(v, str) and v.strip():
                con = v.strip()
                break
        if zh and con:
            anchors[_norm_anchor_key(zh)] = con
    return anchors


def load_translation_anchors(path: Path) -> Tuple[Dict[str, str], int]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)

    if isinstance(data, list):
        anchors = _from_list_records(data)
        return anchors, len(anchors)

    if isinstance(data, dict):
        nested = data.get("anchors")
        if isinstance(nested, dict):
            merged: Dict[str, str] = {}
            for k, v in nested.items():
                if isinstance(k, str) and isinstance(v, str) and v.strip():
                    merged[_norm_anchor_key(k)] = v.strip()
            if merged:
                return merged, len(merged)

        hist = data.get("history") or data.get("records")
        if isinstance(hist, list):
            anchors = _from_list_records(hist)
            if anchors:
                return anchors, len(anchors)

        flat = _pair_from_mapping_like(data)
        return flat, len(flat)

    return {}, 0
