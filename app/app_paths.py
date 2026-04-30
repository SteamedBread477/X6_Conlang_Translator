"""
应用路径工具模块。

PyInstaller 打包后 __file__ 指向临时解压目录 (sys._MEIPASS),
而非 exe 旁边。此模块提供统一的路径获取函数，
确保 data 目录始终在 exe（或开发模式项目根目录）旁边。

- 开发模式：返回项目根目录 (app 包的 parent)
- frozen 模式：返回 exe 所在目录
"""
from __future__ import annotations

import sys
from pathlib import Path


def get_app_dir() -> Path:
    """返回应用程序根目录（exe 旁边 / 项目根目录）。

    - PyInstaller 打包 (frozen): exe 所在目录
    - 正常开发运行: app 包的 parent（即项目根目录）
    """
    if getattr(sys, "frozen", False):
        # PyInstaller frozen mode — exe 所在目录
        return Path(sys.executable).resolve().parent
    # 开发模式 — 项目根目录 (app 包的上一级)
    return Path(__file__).resolve().parent.parent


def get_data_dir() -> Path:
    """返回 data 目录路径，并确保目录存在。

    位置: get_app_dir() / "data"
    """
    data_dir = get_app_dir() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_config_path() -> Path:
    """返回 app_config.json 路径（exe 旁边，而非 data 目录内）。

    位置: get_app_dir() / "app_config.json"
    """
    return get_app_dir() / "app_config.json"