"""
字体偏好配置存取模块。

配置文件：app_config.json（exe 旁边）
字体配置存储在 "font_settings" 子段中，与 paperhub 等其他配置共存。

格式示例：
{
  "font_settings": {
    "family_override": "",           // 空=跟随主题默认字体族
    "size_scale": 1.0,               // 1.0=默认, 0.8=缩小20%, 1.3=放大30%
    "size_offsets": {                 // 预留：后续版本解锁偏移微调
      "button": 0,                   // ±3px 按钮字号偏移
      "title": 0,                    // ±3px 标题字号偏移
      "input": 0                     // ±3px 输入框字号偏移
    }
  },
  "paperhub_enabled": true,
  ...
}

写入策略：读取整个 app_config.json → 仅更新 font_settings 字段 → 写回，
确保不破坏 paperhub 等其他配置段。
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from app.app_paths import get_app_dir

# ── 默认值 ──────────────────────────────────────────────────────────

DEFAULT_FONT_SETTINGS: Dict[str, Any] = {
    "family_override": "",
    "size_scale": 1.0,
    "size_offsets": {
        "button": 0,
        "title": 0,
        "input": 0,
    },
}

# ── 路径 ────────────────────────────────────────────────────────────

def _config_path() -> Path:
    """app_config.json 位于 exe 旁边（而非 data 目录内）。"""
    return (get_app_dir() / "app_config.json").resolve()


# ── 读取 ────────────────────────────────────────────────────────────

def load_font_settings() -> Dict[str, Any]:
    """加载字体偏好配置，缺失字段以默认值补全。"""
    path = _config_path()
    merged = deepcopy(DEFAULT_FONT_SETTINGS)
    if path.is_file():
        try:
            with path.open("r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                fs = stored.get("font_settings", {})
                if isinstance(fs, dict):
                    # 顶层字段合并
                    for k in ("family_override", "size_scale"):
                        if k in fs:
                            merged[k] = fs[k]
                    # size_offsets 子段合并
                    if "size_offsets" in fs and isinstance(fs["size_offsets"], dict):
                        for k in DEFAULT_FONT_SETTINGS["size_offsets"]:
                            if k in fs["size_offsets"]:
                                merged["size_offsets"][k] = fs["size_offsets"][k]
        except (json.JSONDecodeError, OSError):
            pass
    # 类型安全
    merged["family_override"] = str(merged.get("family_override", ""))
    merged["size_scale"] = float(merged.get("size_scale", 1.0))
    merged["size_scale"] = max(0.8, min(1.3, merged["size_scale"]))
    for k in merged["size_offsets"]:
        merged["size_offsets"][k] = int(merged["size_offsets"].get(k, 0))
        merged["size_offsets"][k] = max(-3, min(3, merged["size_offsets"][k]))
    return merged


# ── 写入 ────────────────────────────────────────────────────────────

def save_font_settings(settings: Dict[str, Any]) -> None:
    """将字体偏好配置写入 app_config.json（exe 旁边）。

    读取整个文件 → 仅更新 font_settings 字段 → 写回，
    不破坏 paperhub / ask_templates 等其他配置段。
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # 读取现有配置
    existing: dict = {}
    if path.is_file():
        try:
            with path.open("r", encoding="utf-8") as fh:
                existing = json.load(fh)
            if not isinstance(existing, dict):
                existing = {}
        except (json.JSONDecodeError, OSError):
            existing = {}

    # 合并字体设置
    out = deepcopy(DEFAULT_FONT_SETTINGS)
    for k in ("family_override", "size_scale"):
        if k in settings:
            out[k] = settings[k]
    out["family_override"] = str(out.get("family_override", ""))
    out["size_scale"] = float(out.get("size_scale", 1.0))
    out["size_scale"] = max(0.8, min(1.3, out["size_scale"]))
    if "size_offsets" in settings and isinstance(settings["size_offsets"], dict):
        for k in DEFAULT_FONT_SETTINGS["size_offsets"]:
            if k in settings["size_offsets"]:
                out["size_offsets"][k] = settings["size_offsets"][k]
        for k in out["size_offsets"]:
            out["size_offsets"][k] = max(-3, min(3, int(out["size_offsets"][k])))

    existing["font_settings"] = out
    with path.open("w", encoding="utf-8") as fh:
        json.dump(existing, fh, ensure_ascii=False, indent=2)