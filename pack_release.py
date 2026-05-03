"""
打包发布脚本 — 将 PyInstaller onedir 输出 + 用户数据整合为完整发布目录。

执行流程：
  1. 调用 PyInstaller 生成 onedir 输出到 dist/Nikki Conlang Forge/
  2. 将源码 assets/ 复制到 exe 旁边（覆盖打包内置的精简版）
  3. 将源码 data/ 复制到 exe 旁边（含 3 种语言 + config.json）
  4. 删除不应分发的文件（app_config.json 含 API Key）
  5. 输出最终发布目录清单

使用方式：
  python pack_release.py          # 完整打包（含 PyInstaller 步骤）
  python pack_release.py --skip-build  # 跳过 PyInstaller，仅做文件收集
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

# 项目根目录（此脚本所在目录）
PROJECT_ROOT = Path(__file__).resolve().parent

# PyInstaller onedir 输出目录
DIST_DIR = PROJECT_ROOT / "dist" / "Nikki Conlang Forge"

# 源码路径
SRC_ASSETS = PROJECT_ROOT / "assets"
SRC_DATA = PROJECT_ROOT / "data"

# 排除的文件/目录（不应随安装包分发）
EXCLUDE_FROM_DATA = {
    "languages",  # 空目录（历史遗留）
}

# 不分发的文件模式（在 data 子目录内排除）
EXCLUDE_PATTERNS_IN_DATA_SUBDIRS = {
    "derived",  # derived/material_snapshot.json 是运行时生成的缓存
}


def ensure_app_icon_ico() -> None:
    """确保 assets/app_icon.ico 存在（供 build.spec icon= 参数使用）。

    app_icon.ico 是从 app_icon.jpg 在运行时转换的，且被 .gitignore 排除。
    在全新 clone 上首次打包时 .ico 不存在，会导致 PyInstaller 的 icon= 参数失败。
    此函数在 PyInstaller 之前用 Pillow 将 jpg 转为 ico。
    """
    ico_path = SRC_ASSETS / "app_icon.ico"
    jpg_path = SRC_ASSETS / "app_icon.jpg"

    if ico_path.is_file():
        # .ico 已存在且比 jpg 新 → 无需重新转换
        if ico_path.stat().st_mtime >= jpg_path.stat().st_mtime:
            print("[0/5] app_icon.ico 已存在，跳过转换")
            return

    if not jpg_path.is_file():
        print(f"[错误] 图标源文件不存在: {jpg_path}")
        sys.exit(1)

    try:
        from PIL import Image
        img = Image.open(str(jpg_path))
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
        print(f"[0/5] 已生成 {ico_path}（多尺寸 ICO）")
    except ImportError:
        print("[警告] Pillow 不可用，无法生成 app_icon.ico")
        print("  PyInstaller 的 icon= 参数将回退到无图标 EXE")
        # 不退出——PyInstaller 会生成无图标 EXE（不会崩溃）


def run_pyinstaller() -> None:
    """执行 PyInstaller onedir 打包。"""
    venv_pyinstaller = PROJECT_ROOT / "venv" / "Scripts" / "pyinstaller.exe"
    cmd = [
        str(venv_pyinstaller),
        str(PROJECT_ROOT / "build.spec"),
        "--clean",
        "--noconfirm",
    ]
    print(f"[1/5] 执行 PyInstaller: {cmd}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        print(f"[错误] PyInstaller 失败 (exit code {result.returncode})")
        sys.exit(1)
    print("[1/5] PyInstaller 完成")


def copy_assets() -> None:
    """将源码 assets/ 复制到 exe 旁边（覆盖打包内置的精简版）。

    打包内置的 _internal/assets/ 仅包含 app_icon.jpg + app_icon.ico + icons/ + lang_icons/，
    但缺少 lang_icons 下的所有图标 PNG（PyInstaller datas 只打包了整个 assets 目录）。
    此步骤确保 exe 旁边有完整的外部 assets/ 供用户替换。
    """
    dest_assets = DIST_DIR / "assets"
    print(f"[2/5] 复制 assets: {SRC_ASSETS} → {dest_assets}")

    # 清空目标 assets 目录（避免残留旧文件）
    if dest_assets.exists():
        shutil.rmtree(dest_assets)

    shutil.copytree(SRC_ASSETS, dest_assets)

    # 保留 app_icon.ico（由 ensure_app_icon_ico() 在打包前预生成，
    # 运行时若源文件更新也会重新转换，但保留预生成版本确保可用性）

    # 统计
    lang_icons = dest_assets / "lang_icons"
    icons = dest_assets / "icons"
    lang_icon_count = len(list(lang_icons.glob("*"))) if lang_icons.exists() else 0
    icon_count = len(list(icons.glob("*"))) if icons.exists() else 0
    print(f"  lang_icons: {lang_icon_count} 个图标, icons: {icon_count} 个图标")


def copy_data() -> None:
    """将源码 data/ 复制到 exe 旁边（含语言数据包 + config.json）。

    排除：
      - data/languages/（空目录，历史遗留）
      - data/*/derived/（运行时生成的缓存快照）
    """
    dest_data = DIST_DIR / "data"
    print(f"[3/5] 复制 data: {SRC_DATA} → {dest_data}")

    # 清空目标 data 目录
    if dest_data.exists():
        shutil.rmtree(dest_data)

    # 复制 config.json
    dest_data.mkdir(parents=True, exist_ok=True)
    src_config = SRC_DATA / "config.json"
    if src_config.is_file():
        shutil.copy2(src_config, dest_data / "config.json")
        print("  已复制 config.json")
    else:
        print("[警告] config.json 不存在！首次运行将创建默认语言")

    # 复制语言子目录（排除空目录和 derived 缓存）
    for child in SRC_DATA.iterdir():
        if not child.is_dir():
            continue
        if child.name in EXCLUDE_FROM_DATA:
            print(f"  已跳过: {child.name}（排除列表）")
            continue

        dest_lang = dest_data / child.name
        shutil.copytree(child, dest_lang, ignore=shutil.ignore_patterns(*EXCLUDE_PATTERNS_IN_DATA_SUBDIRS))

        # 统计语言包内容
        files = [f.name for f in dest_lang.iterdir() if f.is_file()]
        print(f"  已复制语言包: {child.name} → {files}")

    # 确保空 languages 目录不会被创建
    lang_dir = dest_data / "languages"
    if lang_dir.exists():
        shutil.rmtree(lang_dir)


def cleanup() -> None:
    """清理不应分发的敏感数据，保留用户自定义配置（如 ask_templates、font_settings）。"""
    print("[4/5] 清理不应分发的敏感数据")

    # app_config.json 中含 API Key 等敏感字段，但也含用户自定义的
    # ask_templates（词作模版）和 font_settings 等非敏感数据。
    # 做法：先将项目根目录的 app_config.json 复制到 dist → 再清除敏感字段 → 保留其余。

    # 先从项目根目录复制最新的 app_config.json（含词作模版等用户数据）
    src_app_config = PROJECT_ROOT / "app_config.json"
    app_config = DIST_DIR / "app_config.json"
    if src_app_config.is_file():
        shutil.copy2(src_app_config, app_config)
        print("  已从项目根目录复制 app_config.json（含词作模版等用户数据）")

    SENSITIVE_KEYS = {
        "paperhub_api_key",       # API Key，绝对不能分发
        "paperhub_enabled",       # 是否启用，用户首次运行应手动开启
    }

    if app_config.is_file():
        try:
            with app_config.open("r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            if isinstance(cfg, dict):
                removed = [k for k in SENSITIVE_KEYS if k in cfg]
                for k in removed:
                    cfg.pop(k, None)
                # 如果清除后还有内容（如 ask_templates / font_settings），写回
                if cfg:
                    with app_config.open("w", encoding="utf-8") as fh:
                        json.dump(cfg, fh, ensure_ascii=False, indent=2)
                    print(f"  已从 app_config.json 中移除敏感字段: {removed}")
                    kept = [k for k in cfg if k not in SENSITIVE_KEYS]
                    print(f"  已保留用户自定义字段: {kept}")
                else:
                    app_config.unlink()
                    print("  app_config.json 仅含敏感字段，已整体删除")
            else:
                app_config.unlink()
                print("  app_config.json 格式异常，已删除")
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  app_config.json 处理失败: {exc}，已删除")
            app_config.unlink(missing_ok=True)

    # 删除 dist 根目录下的残留（如果存在）
    dist_root = PROJECT_ROOT / "dist"
    for residue in dist_root.iterdir():
        if residue.is_file() and residue.name != "Nikki Conlang Forge":
            # dist根目录下可能有之前onefile模式留下的exe
            if residue.suffix == ".exe" or residue.name == "app_config.json":
                residue.unlink()
                print(f"  已删除残留: {residue.name}")

    # 确保 dist 目录下只有 Nikki Conlang Forge/ 子目录
    for item in dist_root.iterdir():
        if item.is_dir() and item.name != "Nikki Conlang Forge":
            # 删除旧的 data/、assets/ 残留
            print(f"  已删除残留目录: {item.name}")
            shutil.rmtree(item)


def print_summary() -> None:
    """输出发布目录清单。"""
    print("\n" + "=" * 60)
    print("  发布目录清单")
    print("=" * 60)

    # exe
    exe = DIST_DIR / "Nikki Conlang Forge.exe"
    exe_size = exe.stat().st_size / (1024 * 1024) if exe.exists() else 0
    print(f"  exe: {exe_size:.1f} MB")

    # _internal
    internal = DIST_DIR / "_internal"
    internal_size = sum(f.stat().st_size for f in internal.rglob("*") if f.is_file()) / (1024 * 1024)
    print(f"  _internal: {internal_size:.1f} MB (运行时依赖)")

    # assets
    assets = DIST_DIR / "assets"
    if assets.exists():
        icons = len(list((assets / "icons").glob("*"))) if (assets / "icons").exists() else 0
        lang_icons = len(list((assets / "lang_icons").glob("*"))) if (assets / "lang_icons").exists() else 0
        print(f"  assets/icons: {icons} 个, assets/lang_icons: {lang_icons} 个")

    # data
    data = DIST_DIR / "data"
    if data.exists():
        config = data / "config.json"
        if config.exists():
            with config.open("r", encoding="utf-8") as f:
                cfg = json.load(f)
            langs = cfg.get("languages", [])
            print(f"  data/config.json: {len(langs)} 种语言")
            for lang in langs:
                print(f"    - {lang.get('name', '?')} (icon: {lang.get('icon', '空')})")

    # app_config.json 不应存在
    app_config = DIST_DIR / "app_config.json"
    if app_config.exists():
        try:
            with app_config.open("r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            non_sensitive = [k for k in cfg if k not in {"paperhub_api_key", "paperhub_enabled"}]
            print(f"  app_config.json: 存在（含 {non_sensitive}，敏感字段已清除）")
        except Exception:
            print("  app_config.json: 存在（无法读取内容）")
    else:
        print("  app_config.json: 不存在（首次运行将自动创建）")

    # 总大小
    total_size = sum(f.stat().st_size for f in DIST_DIR.rglob("*") if f.is_file()) / (1024 * 1024)
    print(f"\n  总大小: {total_size:.1f} MB")
    print(f"  发布目录: {DIST_DIR}")
    print("=" * 60)


def ensure_nsi_bom() -> None:
    """确保 installer.nsi 是 UTF-8 with BOM 编码（NSIS Unicode 模式要求）。

    write_file / 大多数编辑器输出 UTF-8 无 BOM，而 NSIS Unicode 模式
    在编译时需要 UTF-8 BOM 前缀（0xEF 0xBB 0xBF），否则报
    "Bad text encoding" 错误。此函数检测并补充 BOM。
    """
    nsi_path = PROJECT_ROOT / "installer.nsi"
    if not nsi_path.is_file():
        print("[警告] installer.nsi 不存在，跳过 BOM 转换")
        return

    content = nsi_path.read_bytes()
    bom = b"\xef\xbb\xbf"
    if content[:3] == bom:
        print("  installer.nsi 已是 UTF-8 BOM，无需转换")
        return

    nsi_path.write_bytes(bom + content)
    print("  已转换 installer.nsi 为 UTF-8 BOM 编码")


def main() -> None:
    parser = argparse.ArgumentParser(description="打包发布脚本")
    parser.add_argument("--skip-build", action="store_true", help="跳过 PyInstaller 步骤，仅做文件收集")
    args = parser.parse_args()

    if not args.skip_build:
        ensure_app_icon_ico()
        run_pyinstaller()
    else:
        print("[1/5] 跳过 PyInstaller（--skip-build）")
        if not DIST_DIR.exists():
            print(f"[错误] 发布目录不存在: {DIST_DIR}")
            print("请先运行不带 --skip-build 的打包，或手动执行 PyInstaller")
            sys.exit(1)

    copy_assets()
    copy_data()
    cleanup()
    ensure_nsi_bom()
    print_summary()


if __name__ == "__main__":
    main()