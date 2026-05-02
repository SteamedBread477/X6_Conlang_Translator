"""
X6 Conlang Translator (Nikki Conlang Forge) 入口点。

支持两种运行模式：
  1. 正常开发模式：python main.py
  2. PyInstaller 打包模式：双击 exe 运行
"""
import sys
import os

# 确保 app 包可被找到（PyInstaller frozen 模式下 sys.path 可能缺少项目根目录）
if getattr(sys, "frozen", False):
    # PyInstaller frozen — 将 exe 所在目录加入 sys.path
    _exe_dir = os.path.dirname(sys.executable)
    if _exe_dir not in sys.path:
        sys.path.insert(0, _exe_dir)
else:
    # 开发模式 — 确保项目根目录在 sys.path
    _project_root = os.path.dirname(os.path.abspath(__file__))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)


def main() -> int:
    try:
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import Qt
        from app.main_window import MainWindow
    except ImportError as exc:
        # 打包模式下缺失依赖时给出友好提示
        print(f"启动失败：缺少必要依赖库\n{exc}")
        print("请联系开发者获取完整版本。")
        if not getattr(sys, "frozen", False):
            print("开发模式请运行: pip install -r requirements.txt")
        return 1

    # 启用高 DPI 缩放，让 Qt 根据 OS 设置自动放大控件和字体
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Nikki Conlang Forge")
    app.setOrganizationName("X6")

    # 设置 Windows 任务栏 AppUserModelID（确保任务栏图标正确显示）
    try:
        from PyQt5.QtWinExtras import QWinTaskbarButton  # noqa
    except ImportError:
        pass  # PyQt5.QtWinExtras 不可用时忽略
    if hasattr(app, "setWindowIcon") or True:
        # Windows 任务栏需要 AppUserModelID 来关联图标
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "X6.NikkiConlangForge"
            )
        except Exception:
            pass

    # 设置应用级默认图标（影响任务栏、系统通知等）
    from app.app_paths import get_icon_ico_path, get_icon_source_path
    from PyQt5.QtGui import QIcon
    icon_path = get_icon_ico_path()
    if not icon_path or not str(icon_path):
        icon_path = get_icon_source_path()
    if icon_path and str(icon_path):
        app_icon = QIcon(str(icon_path))
        if not app_icon.isNull():
            app.setWindowIcon(app_icon)

    # 应用主题（全局 QSS + 旧兼容层同步）
    from app.ui_theme import theme_manager, UITheme
    theme_manager.apply(app)
    UITheme.sync_from_manager()

    # 加载字体偏好覆写（若有）
    from app.font_settings import load_font_settings
    fs = load_font_settings()
    family = fs.get("family_override", "")
    scale = fs.get("size_scale", 1.0)
    if family or scale != 1.0:
        theme_manager.apply_font_override(fs)

    window = MainWindow()
    window.show()

    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())