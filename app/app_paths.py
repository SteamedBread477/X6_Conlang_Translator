"""
应用路径工具模块。

PyInstaller onedir 模式打包后目录结构：
  exe 所在目录/
    Nikki Conlang Forge.exe        ← 主程序入口
    _internal/                     ← PyInstaller 运行时 (sys._MEIPASS)
    assets/                        ← 外部资源（优先，用户可替换）
    data/                          ← 语言数据包
    app_config.json                ← 用户配置

此模块提供统一的路径获取函数，确保 assets/data 等目录
始终在 exe 旁边（而非 _internal 内部）。

资源查找优先级：
  1. exe 旁边的外部 assets/（用户可替换图标、lang_icons 等）
  2. _internal/assets/（打包内置的回退，仅在外部缺失时使用）

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
}


def get_icons_dir() -> Path:
    """返回 assets/icons 目录路径，并确保目录存在。

    位置: get_assets_dir() / "icons"
    """
    icons_dir = get_assets_dir() / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    return icons_dir


def get_lang_icons_dir() -> Path:
    """返回 assets/lang_icons 目录路径，并确保目录存在。

    位置: get_assets_dir() / "lang_icons"
    用户可将语言图标（PNG/JPG 等）放入此目录，
    程序会列出所有图片供用户在语言列表中选择。
    """
    lang_icons_dir = get_assets_dir() / "lang_icons"
    lang_icons_dir.mkdir(parents=True, exist_ok=True)
    return lang_icons_dir


def get_icon_path(icon_key: str) -> Path:
    """根据 ICON_MAP 的 key 返回对应图标文件的完整路径。

    若文件不存在则返回空 Path（调用方应做回退处理）。
    """
    filename = ICON_MAP.get(icon_key)
    if not filename:
        return Path()
    path = get_icons_dir() / filename
    return path if path.is_file() else Path()


def _has_any_image(directory: Path) -> bool:
    """检查目录中是否存在任何图片文件（app_icon.* 或 icons/、lang_icons/）。"""
    if any(directory.glob("app_icon.*")):
        return True
    icons = directory / "icons"
    if icons.is_dir() and any(icons.iterdir()):
        return True
    lang_icons = directory / "lang_icons"
    if lang_icons.is_dir() and any(lang_icons.iterdir()):
        return True
    return False


def get_assets_dir() -> Path:
    """返回 assets 目录路径（优先外部，回退打包内置）。

    查找优先级：
      1. exe 旁边的外部 assets/ — 用户可替换图标、语言图标等
      2. _internal/assets/ (sys._MEIPASS) — PyInstaller 打包内置的回退

    onedir 模式下，pack_release.py 会将 assets 复制到 exe 旁边，
    程序优先使用外部目录（用户可替换）。若外部目录完全空
    （无任何图片文件），则回退到打包内置资源。
    """
    # 外部 assets（exe 旁边，用户可替换）
    external_assets = get_app_dir() / "assets"
    external_assets.mkdir(parents=True, exist_ok=True)

    if _has_any_image(external_assets):
        return external_assets

    # frozen 模式下，外部 assets 完全空时回退到打包内置
    if getattr(sys, "frozen", False):
        meipass_assets = Path(sys._MEIPASS) / "assets"
        if meipass_assets.is_dir() and _has_any_image(meipass_assets):
            return meipass_assets

    # 开发模式或无法回退时，使用外部目录（即使为空）
    return external_assets


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
        # RGBA 图像需转为 RGB（ICO 格式不支持 alpha 通道）
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        # Pillow 11+ 直接在 save() 时传 sizes 参数，内部自动 resize
        img.save(
            str(ico_path),
            format="ICO",
            sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
        return ico_path
    except Exception:
        # Pillow 不可用或转换失败 → 返回源路径（PyQt5 可直接加载 jpg/png）
        return source