"""
PaperHub AI 配置存取模块。

配置文件：data/app_config.json
格式示例：
{
  "paperhub_enabled": true,
  "paperhub_api_key": "sk-xxx",
  "paperhub_base_url": "https://tc-paperhub.diezhi.net/v1",
  "paperhub_model": "qwen3-max",
  "paperhub_strategy": "unmatched_only",
  "paperhub_reasoning_enabled": true,
  "paperhub_temperature": 0.7,
  "paperhub_max_tokens": 2048
}
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

DEFAULT_PAPERHUB_SETTINGS: Dict[str, Any] = {
    "paperhub_enabled": False,
    "paperhub_api_key": "",
    "paperhub_base_url": "https://tc-paperhub.diezhi.net/v1",
    "paperhub_model": "qwen3-max",
    "paperhub_strategy": "unmatched_only",   # unmatched_only | always | confirm
    "paperhub_reasoning_enabled": True,
    "paperhub_temperature": 0.7,
    "paperhub_max_tokens": 2048,
}

# PaperHub 可用模型清单（显示名, 模型 ID, 描述）
PAPERHUB_MODELS = [
    ("qwen3-max",          "qwen3-max",          "通用对话 / Agent，已签保密协议"),
    ("glm-5",              "glm-5",              "代码与工程能力，适合研发类任务，已签保密协议"),
    ("doubao-seed-2-0-pro","doubao-seed-2-0-pro","多模态推理，已签保密协议"),
    ("qwen3.5-plus",       "qwen3.5-plus",       "多模态理解，已签保密协议"),
]

PAPERHUB_DASHBOARD_URL = "https://tc-paperhub.diezhi.net/dashboard"
PAPERHUB_DEFAULT_BASE_URL = "https://tc-paperhub.diezhi.net/v1"


def _config_path(base_dir: Path) -> Path:
    return (base_dir / "app_config.json").resolve()


def load_paperhub_settings(base_dir: Path) -> Dict[str, Any]:
    """加载 PaperHub 配置，缺失字段以默认值补全。"""
    path = _config_path(base_dir)
    merged = deepcopy(DEFAULT_PAPERHUB_SETTINGS)
    if path.is_file():
        try:
            with path.open("r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                merged.update(
                    {k: v for k, v in stored.items() if k in DEFAULT_PAPERHUB_SETTINGS}
                )
        except (json.JSONDecodeError, OSError):
            pass
    return merged


def save_paperhub_settings(base_dir: Path, settings: Dict[str, Any]) -> None:
    """将 PaperHub 配置写入 data/app_config.json。"""
    path = _config_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = deepcopy(DEFAULT_PAPERHUB_SETTINGS)
    out.update({k: v for k, v in settings.items() if k in DEFAULT_PAPERHUB_SETTINGS})
    # 确保数值类型正确
    out["paperhub_temperature"] = float(out["paperhub_temperature"])
    out["paperhub_max_tokens"] = int(out["paperhub_max_tokens"])
    out["paperhub_enabled"] = bool(out["paperhub_enabled"])
    out["paperhub_reasoning_enabled"] = bool(out["paperhub_reasoning_enabled"])
    with path.open("w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
