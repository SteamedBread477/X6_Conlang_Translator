"""
集中存放界面外观相关常量，便于后续统一换字体、配色、图标方案。

使用方式：main_window / 其他组件从此模块读取颜色与预留槽位，
避免样式散落在各处。
"""

from __future__ import annotations


class UITheme:
    # 资料加载状态颜色（可用于 QLabel 的富文本或后续 QSS）
    STATUS_OK_COLOR = "#2e7d32"
    STATUS_MISSING_COLOR = "#757575"
    STATUS_ERROR_COLOR = "#c62828"

    # 预留：后续可在应用启动时统一下发到 qApp.setFont / 样式表
    FONT_FAMILY: str | None = None
    BASE_FONT_POINT_SIZE: int | None = None

    # 预留：图标资源根路径（Qt 资源或文件路径前缀）
    ICON_THEME_PREFIX: str | None = None

    # 预留：主要按钮配色（后续可生成 QSS 片段）
    BUTTON_ACCENT_BG: str | None = None
    # 预留：AI 请求期间状态栏/对话框的文案主题（便于与主样式表统一）
    AI_STATUS_PREFIX: str | None = None
