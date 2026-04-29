from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

DEFAULT_AI_SETTINGS: Dict[str, Any] = {
    "enabled": False,
    "provider": "claude",
    "claude_api_key": "",
    "claude_model": "claude-sonnet-4-20250514",
    "gemini_api_key": "",
    "gemini_model": "gemini-2.0-flash",
    "ai_for_oov_only": True,
}


def ai_settings_path(data_dir: Path) -> Path:
    return (data_dir / "ai_settings.json").resolve()


def load_ai_settings(data_dir: Path) -> Dict[str, Any]:
    path = ai_settings_path(data_dir)
    if not path.is_file():
        return deepcopy(DEFAULT_AI_SETTINGS)
    with path.open("r", encoding="utf-8") as handle:
        merged = deepcopy(DEFAULT_AI_SETTINGS)
        merged.update(json.load(handle))
        return merged


def save_ai_settings(data_dir: Path, settings: Dict[str, Any]) -> None:
    path = ai_settings_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = deepcopy(DEFAULT_AI_SETTINGS)
    out.update(settings)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(out, handle, ensure_ascii=False, indent=2)
