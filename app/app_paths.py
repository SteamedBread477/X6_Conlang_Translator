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


# ------------------------------------------------------------------
# 应用图标路径（可替换）
# ------------------------------------------------------------------

# 图标源文件名 —— 用户可直接替换 assets/ 下的同名文件，
# 支持 jpg / png / ico 格式，首次运行会自动转换为 .ico。
ICON_SOURCE_NAME: str = "app_icon.jpg"

# ------------------------------------------------------------------
# 图标映射表（assets/icons/ 目录）
# ------------------------------------------------------------------
# key   → 用途描述（用于代码中引用）
# value → assets/icons/ 下的文件名（png/svg 等格式）
ICON_MAP: dict[str, str] = {
    "confirm":   "confirm.png",      # ✓ 确认操作
    "discard":   "discard.png",      # ✗ 丢弃/删除操作
    "copy":      "copy.png",         # 复制操作
    "translate": "translate.png",    # 翻译操作
}


def get_icons_dir() -> Path:
    """返回 assets/icons 目录路径，并确保目录存在。

    位置: get_assets_dir() / "icons"
    """
    icons_dir = get_assets_dir() / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    return icons_dir


def get_icon_path(icon_key: str) -> Path:
    """根据 ICON_MAP 的 key 返回对应图标文件的完整路径。

    若文件不存在则返回空 Path（调用方应做回退处理）。
    """
    filename = ICON_MAP.get(icon_key)
    if not filename:
        return Path()
    path = get_icons_dir() / filename
    return path if path.is_file() else Path()


def get_assets_dir() -> Path:
    """返回 assets 目录路径，并确保目录存在。

    位置: get_app_dir() / "assets"

    PyInstaller 打包后，exe 旁边的 assets 目录可能为空（图标等资源打包在内部），
    此时回退到 sys._MEIPASS 下的 assets 目录以确保能找到图标等资源。
    """
    assets_dir = get_app_dir() / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    # frozen 模式下，若外部 assets 目录无图标文件，回退到打包内部
    if getattr(sys, "frozen", False):
        has_icon = any(assets_dir.glob("app_icon.*"))
        if not has_icon:
            meipass_assets = Path(sys._MEIPASS) / "assets"
            if meipass_assets.is_dir() and any(meipass_assets.glob("app_icon.*")):
                return meipass_assets

    return assets_dir


def get_icon_source_path() -> Path:
    """返回图标源文件路径（assets/<ICON_SOURCE_NAME>）。

    如果 ICON_SOURCE_NAME 指向的文件不存在，会在 assets/ 中
    查找 jpg/png/ico 等替代文件并返回第一个匹配项。
    若仍无匹配则返回空 Path。
    """
    assets = get_assets_dir()
    primary = assets / ICON_SOURCE_NAME
    if primary.is_file():
        return primary

    # 源文件不存在时，按扩展名优先级查找替代图标
    for ext in ("ico", "png", "jpg", "jpeg"):
        for candidate in assets.glob(f"app_icon.{ext}"):
            if candidate.is_file():
                return candidate
    return Path()


def get_icon_ico_path() -> Path:
    """返回 .ico 图标文件路径（供 Windows 任务栏 / 窗口图标使用）。

    若源文件本身已是 .ico 则直接返回源路径；
    否则自动将 jpg/png 源文件转换为 assets/app_icon.ico
    （仅在 .ico 不存在或源文件更新时才重新转换）。
    """
    source = get_icon_source_path()
    if not source:
        return Path()

    # 源文件本身就是 .ico → 直接使用
    if source.suffix.lower() == ".ico":
        return source

    ico_path = get_assets_dir() / "app_icon.ico"

    # .ico 已存在且比源文件新 → 无需重新转换
    if ico_path.is_file() and ico_path.stat().st_mtime >= source.stat().st_mtime:
        return ico_path

    # 尝试使用 Pillow 在运行时转换
    try:
        from PIL import Image  # type: ignore
        img = Image.open(str(source))
        # ICO 格式需要尺寸为 16/32/48/64/128/256 的正方形
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        resized = []
        for w, h in sizes:
            resized.append(img.resize((w, h), Image.LANCZOS))
        resized[0].save(
            str(ico_path),
            format="ICO",
            sizes=[(s.width, s.height) for s in resized],
            append_images=resized[1:],
        )
        return ico_path
    except Exception:
        # Pillow 不可用或转换失败 → 返回源路径（PyQt5 可直接加载 jpg/png）
        return source