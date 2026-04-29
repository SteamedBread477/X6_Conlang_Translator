from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

AssetStatus = Literal["missing", "ok", "error"]


@dataclass
class AssetCheckResult:
    status: AssetStatus
    message: str = ""


def check_whitepaper(path: Path) -> AssetCheckResult:
    if not path.is_file():
        return AssetCheckResult("missing")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return AssetCheckResult("error", str(exc))
    if not text.strip():
        return AssetCheckResult("error", "文件为空或仅空白")
    return AssetCheckResult("ok")


def check_json_file(path: Path) -> AssetCheckResult:
    if not path.is_file():
        return AssetCheckResult("missing")
    try:
        raw = path.read_text(encoding="utf-8")
        json.loads(raw)
    except OSError as exc:
        return AssetCheckResult("error", str(exc))
    except json.JSONDecodeError as exc:
        return AssetCheckResult("error", f"JSON 无效：{exc}")
    return AssetCheckResult("ok")


def check_mapping_csv(path: Path) -> AssetCheckResult:
    if not path.is_file():
        return AssetCheckResult("missing")
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.reader(handle))
    except OSError as exc:
        return AssetCheckResult("error", str(exc))
    except csv.Error as exc:
        return AssetCheckResult("error", str(exc))
    if not rows:
        return AssetCheckResult("error", "CSV 无内容")
    return AssetCheckResult("ok")


def check_translation_history(path: Path) -> AssetCheckResult:
    return check_json_file(path)


def check_asset(key: str, path: Path) -> AssetCheckResult:
    if key == "whitepaper":
        return check_whitepaper(path)
    if key == "master_library":
        return check_json_file(path)
    if key == "mapping_rules":
        return check_mapping_csv(path)
    if key == "translation_history":
        return check_translation_history(path)
    return AssetCheckResult("error", f"未知资料类型：{key}")
