from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Dict, List, Tuple


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", "", (h or "").strip())


def _match_columns(headers: List[str]) -> Tuple[int | None, int | None, int | None]:
    """列：自创语词汇, IPA音标, TTS友好拼写（允许轻微变体）。"""
    norm = [_norm_header(h) for h in headers]
    idx_word: int | None = None
    idx_ipa: int | None = None
    idx_tts: int | None = None

    for i, h in enumerate(norm):
        if any(
            key in h
            for key in (
                "自创语词汇",
                "自创语",
                "词汇",
                "词形",
            )
        ):
            idx_word = i
        if "IPA" in h or "ipa" in h.lower() or "音标" in h:
            idx_ipa = i
        if "TTS" in h or "tts" in h.lower() or "友好拼写" in h or "拼写" in h:
            idx_tts = i

    return idx_word, idx_ipa, idx_tts


def load_ipa_mapping(path: Path) -> Tuple[Dict[str, str], int]:
    """建立 自创语 → IPA音标 映射。若文件无 IPA 列则静默返回空字典。"""
    mapping: Dict[str, str] = {}
    count = 0
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    if not rows:
        return {}, 0

    idx_word, idx_ipa, _idx_tts = _match_columns(rows[0])
    if idx_word is None or idx_ipa is None:
        return {}, 0

    for row in rows[1:]:
        if idx_word >= len(row) or idx_ipa >= len(row):
            continue
        word = row[idx_word].strip()
        ipa = row[idx_ipa].strip()
        if not word or not ipa:
            continue
        mapping[word] = ipa
        count += 1
    return mapping, count


def load_tts_mapping(path: Path) -> Tuple[Dict[str, str], int]:
    """建立 自创语 → TTS 友好拼写 映射；IPA 列用于校验存在性，不进入映射。"""
    mapping: Dict[str, str] = {}
    count = 0
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        rows = list(reader)
    if not rows:
        return {}, 0

    idx_word, _idx_ipa, idx_tts = _match_columns(rows[0])
    if idx_word is None or idx_tts is None:
        raise ValueError(
            "CSV 表头需包含「自创语词汇」与「TTS友好拼写」相关列（当前未能匹配列名）。"
        )

    for row in rows[1:]:
        if idx_word >= len(row) or idx_tts >= len(row):
            continue
        word = row[idx_word].strip()
        tts = row[idx_tts].strip()
        if not word or not tts:
            continue
        mapping[word] = tts
        count += 1
    return mapping, count
