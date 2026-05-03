"""
PaperHub AI 配置存取模块。

配置文件：app_config.json（exe 旁边）
格式示例：
{
  "paperhub_enabled": false,
  "paperhub_api_key": "sk-xxx",
  "paperhub_base_url": "https://tc-paperhub.diezhi.net/v1",
  "paperhub_model": "qwen3-max",
  "paperhub_strategy": "unmatched_only",
  "paperhub_reasoning_enabled": false,
  "paperhub_temperature": 0.1,
  "paperhub_max_tokens": 1200,
  "paperhub_timeout": 90,
  "paperhub_stream": true
}

性能说明：
- reasoning_enabled=false（默认）：响应通常 3–8s；启用后预计 30–90s，请同步调大超时。
- max_tokens 建议 800–1500：翻译任务不需要超大 token budget，越小越快。
- stream=true（默认）：流式输出，首 token 即时显示，不会因超时整体失败。
- timeout 建议：关闭思考模式 ≥60s；开启思考模式 ≥120s。
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

from app.app_paths import get_app_dir

DEFAULT_PAPERHUB_SETTINGS: Dict[str, Any] = {
    "paperhub_enabled": False,
    "paperhub_api_key": "",
    "paperhub_base_url": "https://tc-paperhub.diezhi.net/v1",
    "paperhub_model": "qwen3-max",
    "paperhub_strategy": "unmatched_only",   # unmatched_only | always | confirm
    "paperhub_reasoning_enabled": False,     # 默认关闭；开启后响应时间显著增加（30–90s）
    "paperhub_temperature": 0.7,
    "paperhub_max_tokens": 1200,             # 翻译任务够用；越小响应越快
    "paperhub_timeout": 90,                  # 秒；关闭思考模式 ≥60，开启思考模式 ≥120
    "paperhub_stream": True,                 # 流式输出；首 token 即时显示，不受超时整体中断
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

# ASK 模式快捷提问模板默认值
# 每个模板包含 name（显示名）和 prompt（实际提问文本）
DEFAULT_ASK_TEMPLATES: list = [
    {"name": "翻译方案", "prompt": "帮我将以下中文内容翻译成自创语，并给出详细的翻译逻辑："},
    {"name": "风格变体", "prompt": "帮我给以下词汇生成几种不同风格的翻译方案（如正式、口语、祭祀、暗黑等）："},
    {"name": "词源解释", "prompt": "请解释以下自创语词汇的构词逻辑和音系来源："},
]


def _config_path() -> Path:
    """app_config.json 位于 exe 旁边（而非 data 目录内）。"""
    return (get_app_dir() / "app_config.json").resolve()


def load_paperhub_settings() -> Dict[str, Any]:
    """加载 PaperHub 配置，缺失字段以默认值补全。"""
    path = _config_path()
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


def save_paperhub_settings(settings: Dict[str, Any]) -> None:
    """将 PaperHub 配置写入 app_config.json（exe 旁边）。"""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    out = deepcopy(DEFAULT_PAPERHUB_SETTINGS)
    out.update({k: v for k, v in settings.items() if k in DEFAULT_PAPERHUB_SETTINGS})
    # 确保数值类型正确
    out["paperhub_temperature"] = float(out["paperhub_temperature"])
    out["paperhub_max_tokens"] = int(out["paperhub_max_tokens"])
    out["paperhub_timeout"] = max(10, int(out["paperhub_timeout"]))
    out["paperhub_enabled"] = bool(out["paperhub_enabled"])
    out["paperhub_reasoning_enabled"] = bool(out["paperhub_reasoning_enabled"])
    out["paperhub_stream"] = bool(out["paperhub_stream"])
    # paperhub_model 允许为平台返回的任意模型 ID，不限于内置列表
    if settings.get("paperhub_model"):
        out["paperhub_model"] = str(settings["paperhub_model"])
    with path.open("w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)


# ── ASK 快捷提问模板 ──────────────────────────────────────────────


def load_ask_templates() -> list:
    """加载 ASK 快捷提问模板。

    用户自定义模板排在前面，然后追加默认模板中未被用户覆盖的部分。
    """
    path = _config_path()
    user_templates: list = []
    if path.is_file():
        try:
            with path.open("r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                user_templates = stored.get("ask_templates", [])
        except (json.JSONDecodeError, OSError):
            pass

    # 合并：用户模板在前，默认模板中名字未被覆盖的追加到后面
    user_names = {t.get("name") for t in user_templates if isinstance(t, dict)}
    merged = list(user_templates)
    for d in DEFAULT_ASK_TEMPLATES:
        if d["name"] not in user_names:
            merged.append(d)
    return merged


def save_ask_templates(templates: list) -> None:
    """将用户自定义的 ASK 快捷提问模板写入 app_config.json。

    只保存用户手动添加/修改的模板，不保存默认模板。
    """
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # 读取现有配置，仅更新 ask_templates 字段
    existing: dict = {}
    if path.is_file():
        try:
            with path.open("r", encoding="utf-8") as fh:
                existing = json.load(fh)
            if not isinstance(existing, dict):
                existing = {}
        except (json.JSONDecodeError, OSError):
            existing = {}

    # 过滤掉与默认模板完全一致的条目，只保留用户自定义部分
    default_set = {(d["name"], d["prompt"]) for d in DEFAULT_ASK_TEMPLATES}
    user_only = [t for t in templates if isinstance(t, dict)
                 and (t.get("name"), t.get("prompt")) not in default_set]

    existing["ask_templates"] = user_only
    with path.open("w", encoding="utf-8") as fh:
        json.dump(existing, fh, ensure_ascii=False, indent=2)
