"""
历史记录写入器 — 将翻译结果追加到 Translation_History.json。

文件格式：JSON 数组，每条记录遵循以下结构：
{
  "id": "TH_0001",
  "timestamp": "2025-04-29T10:30:00",
  "source": "中文原文",
  "conlang": "自创语文本",
  "phonetic": "TTS友好音译",
  "unmatched_words": ["词1", "词2"],
  "source_language": "中文",
  "target_language": "语言页签名",
  "translation_mode": "rule",
  "emotion": {
    "label": "neutral",
    "intensity": 0.5,
    "tts_pitch_hint": "normal",
    "tts_rate_hint": "normal"
  }
}

兼容初始占位文件（内容为 `{}` 或空）和已有的列表格式。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def _load_history(path: Path) -> List[Dict[str, Any]]:
    """读取历史文件，返回记录列表；处理初始占位及各种遗留格式。"""
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8-sig").strip()
    if not raw or raw in ("{}", "[]"):
        return []
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]

    if isinstance(data, dict):
        for key in ("history", "records", "entries"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                return [r for r in candidate if isinstance(r, dict)]

    return []


def _generate_id(records: List[Dict[str, Any]]) -> str:
    """生成不与已有记录冲突的顺序 ID（如 TH_0001）。"""
    existing: set[str] = {
        r["id"] for r in records if isinstance(r.get("id"), str)
    }
    n = len(records) + 1
    while True:
        candidate = f"TH_{n:04d}"
        if candidate not in existing:
            return candidate
        n += 1


def append_translation_record(
    path: Path,
    *,
    source: str,
    conlang: str,
    phonetic: str,
    unmatched_words: List[str],
    source_language: str = "中文",
    target_language: str = "自创语",
    translation_mode: str = "rule",
    emotion_label: str = "neutral",
    emotion_intensity: float = 0.5,
    tts_pitch_hint: str = "normal",
    tts_rate_hint: str = "normal",
) -> str:
    """
    将翻译记录追加到 Translation_History.json，返回分配的记录 ID。

    若文件不存在或为占位内容，自动创建并初始化为数组格式。
    """
    records = _load_history(path)
    record_id = _generate_id(records)
    record: Dict[str, Any] = {
        "id": record_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "conlang": conlang,
        "phonetic": phonetic,
        "unmatched_words": unmatched_words,
        "source_language": source_language,
        "target_language": target_language,
        "translation_mode": translation_mode,
        "emotion": {
            "label": emotion_label,
            "intensity": round(emotion_intensity, 3),
            "tts_pitch_hint": tts_pitch_hint,
            "tts_rate_hint": tts_rate_hint,
        },
    }
    records.append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return record_id
