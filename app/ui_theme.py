"""
集中存放界面外观主题系统，支持多套可选皮肤。

架构：
  ThemeTokens  — 设计变量抽象层（颜色、字体、圆角、阴影、间距等）
  ThemeDefinition — 具体主题的 token 值映射
  ThemeManager — 全局单例，负责注册主题、切换主题、生成 QSS

使用方式：
  from app.ui_theme import theme_manager
  qss = theme_manager.generate_qss()         # 获取当前主题的全局样式表
  theme_manager.apply(app)                    # 应用到 QApplication
  theme_manager.switch_theme("dark_mode")     # 切换皮肤（自动重新 apply）

组件中绝不硬编码颜色/字号等，一律通过 token 引用：
  token = theme_manager.token("color.primary")
  label.setStyleSheet(f"color: {token};")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from PyQt5.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# Token 定义：设计变量的语义名称
# ---------------------------------------------------------------------------

@dataclass
class ThemeTokens:
    """所有可配置的设计 token，语义命名，与具体皮肤解耦。"""

    # ── 颜色 ──────────────────────────────────────────────────
    # 主色系
    color_primary: str = "#B39DDB"           # 主色（紫罗兰）
    color_primary_hover: str = "#9B84D0"     # 主色悬停
    color_primary_pressed: str = "#8A72C4"   # 主色按下
    color_primary_light: str = "#E8DFF5"     # 主色浅色（用于面板背景）
    color_primary_text: str = "#FFFFFF"       # 主色上的文字颜色

    # 辅色系
    color_secondary: str = "#BFF629"          # 辅色（青柠绿）
    color_secondary_hover: str = "#A8E020"    # 辅色悬停
    color_secondary_light: str = "#E1F5FE"    # 辅色浅色（语言选择区背景）

    # 强调色
    color_highlight: str = "#F4FF81"          # 强调色（导入按钮、复制标签）
    color_highlight_hover: str = "#E0EE70"    # 强调色悬停

    # 背景色
    color_bg_window: str = "#FAFAFA"          # 整体窗体背景
    color_bg_panel: str = "#F5F2FA"           # 左侧面板背景
    color_bg_card: str = "#FFFFFF"            # 卡片/分组框背景
    color_bg_input: str = "#FFFFFF"           # 输入框背景
    color_bg_hover: str = "#F0EDE8"           # 通用悬停背景
    color_bg_selected: str = "#E8DFF5"        # 选中行背景
    color_bg_status_bar: str = "#F0EDE8"      # 状态栏背景

    # 文字色
    color_text_primary: str = "#2D2D2D"       # 主要文字（深炭灰）
    color_text_secondary: str = "#666666"     # 辅助文字
    color_text_muted: str = "#999999"          # 次要/提示文字
    color_text_on_primary: str = "#2D2D2D"    # 主色按钮上的文字
    color_text_on_highlight: str = "#2D2D2D"  # 强调色上的文字

    # 边框色
    color_border: str = "#E0DDD8"             # 通用边框
    color_border_focus: str = "#B39DDB"       # 聚焦边框（=主色）
    color_border_light: str = "#F0EDE8"       # 轻边框（分隔线）

    # 状态色
    color_status_ok: str = "#2e7d32"          # ✓ 成功状态
    color_status_missing: str = "#757575"     # ○ 缺失状态
    color_status_error: str = "#c62828"       # ✗ 错误状态
    color_status_warning: str = "#cc0000"     # 警告
    color_status_info: str = "#0066cc"        # 信息链接

    # ── 字体 ──────────────────────────────────────────────────
    font_family: str = "Segoe UI, Microsoft YaHei, sans-serif"
    font_size_xs: str = "11px"                # 极小（辅助标注）
    font_size_sm: str = "12px"                # 小（统计、提示）
    font_size_base: str = "13px"              # 基础（正文）
    font_size_md: str = "14px"                # 中（标题）
    font_size_lg: str = "16px"                # 大（对话框标题）
    font_size_xl: str = "18px"                # 极大（窗口标题）
    font_weight_normal: str = "normal"
    font_weight_bold: str = "bold"
    font_weight_semi: str = "600"

    # ── 圆角 ──────────────────────────────────────────────────
    radius_none: str = "0px"
    radius_sm: str = "4px"                    # 小圆角（标签、小按钮）
    radius_md: str = "8px"                    # 中圆角（卡片、输入框）
    radius_lg: str = "12px"                   # 大圆角（面板、对话框）
    radius_xl: str = "16px"                   # 极大圆角（主按钮）
    radius_pill: str = "9999px"               # 药丸形（标签、徽章）

    # ── 阴影 ──────────────────────────────────────────────────
    shadow_none: str = "none"
    shadow_sm: str = "0 1px 2px rgba(0,0,0,0.06)"
    shadow_md: str = "0 2px 8px rgba(0,0,0,0.10)"
    shadow_lg: str = "0 4px 16px rgba(0,0,0,0.14)"
    shadow_focus: str = "0 0 0 3px rgba(179,157,219,0.3)"

    # ── 间距 ──────────────────────────────────────────────────
    spacing_xs: str = "4px"
    spacing_sm: str = "6px"
    spacing_md: str = "8px"
    spacing_lg: str = "12px"
    spacing_xl: str = "16px"
    spacing_xxl: str = "24px"

    # ── 尺寸 ──────────────────────────────────────────────────
    button_height_sm: str = "28px"
    button_height_md: str = "36px"
    button_height_lg: str = "44px"
    input_min_height: str = "60px"
    panel_min_width: str = "200px"
    sidebar_width: str = "220px"

    # ── 动画（QSS transition 目前仅部分 Qt 支持，留做预留）──────
    transition_fast: str = "150ms"
    transition_normal: str = "250ms"

    # ── 透明度 / overlay ──────────────────────────────────────
    overlay_light: str = "rgba(0,0,0,0.04)"
    overlay_medium: str = "rgba(0,0,0,0.08)"


# ---------------------------------------------------------------------------
# 主题定义：每个皮肤是一个 ThemeTokens 实例
# ---------------------------------------------------------------------------

def _macaron_purple_theme() -> ThemeTokens:
    """默认主题：极简 SaaS 风 · 马卡龙紫。"""
    return ThemeTokens()


def _dark_mode_theme() -> ThemeTokens:
    """暗色主题（预留，后续可完善）。"""
    return ThemeTokens(
        color_primary="#7E57C2",
        color_primary_hover="#9575CD",
        color_primary_pressed="#6A3E9E",
        color_primary_light="#2A2040",
        color_primary_text="#FFFFFF",
        color_secondary="#BFF629",
        color_secondary_hover="#A8E020",
        color_secondary_light="#1A2A1A",
        color_highlight="#F4FF81",
        color_highlight_hover="#E0EE70",
        color_bg_window="#1E1E2E",
        color_bg_panel="#252536",
        color_bg_card="#2A2A3C",
        color_bg_input="#33334A",
        color_bg_hover="#353550",
        color_bg_selected="#3A3560",
        color_bg_status_bar="#252536",
        color_text_primary="#E0E0E0",
        color_text_secondary="#AAAAAA",
        color_text_muted="#777777",
        color_text_on_primary="#FFFFFF",
        color_text_on_highlight="#2D2D2D",
        color_border="#404060",
        color_border_focus="#7E57C2",
        color_border_light="#353550",
        color_status_ok="#4CAF50",
        color_status_missing="#9E9E9E",
        color_status_error="#EF5350",
        color_status_warning="#EF5350",
        color_status_info="#42A5F5",
    )


# ---------------------------------------------------------------------------
# QSS 生成器：从 tokens 生成完整的 Qt 样式表
# ---------------------------------------------------------------------------

def _generate_qss(tokens: ThemeTokens) -> str:
    """根据 ThemeTokens 生成全局 QSS 样式表。

    QSS 中所有颜色/字号/圆角/间距都引用 token 值，
    切换皮肤只需更换 tokens 实例再重新生成。
    """
    t = tokens  # shorthand

    qss = """
/* ═══════════════════════════════════════════════════════════
   Nikki Conlang Forge — Global QSS (theme-driven)
   Theme: auto-generated from ThemeTokens
   ═══════════════════════════════════════════════════════════ */

/* ── 全局基础 ──────────────────────────────────────────── */
QMainWindow, QDialog {{
    background: {color_bg_window};
    font-family: {font_family};
    font-size: {font_size_base};
    color: {color_text_primary};
}}

QWidget {{
    font-family: {font_family};
    color: {color_text_primary};
}}

QLabel {{
    color: {color_text_primary};
    font-size: {font_size_base};
}}

QLabel[class="title"] {{
    font-weight: {font_weight_bold};
    font-size: {font_size_md};
}}

QLabel[class="heading"] {{
    font-weight: {font_weight_bold};
    font-size: {font_size_lg};
}}

QLabel[class="muted"] {{
    color: {color_text_muted};
    font-size: {font_size_sm};
}}

QLabel[class="secondary"] {{
    color: {color_text_secondary};
    font-size: {font_size_sm};
}}

QLabel[class="link"] {{
    color: {color_status_info};
}}

QLabel[class="status-ok"] {{
    color: {color_status_ok};
    font-weight: {font_weight_bold};
}}

QLabel[class="status-missing"] {{
    color: {color_status_missing};
    font-weight: {font_weight_bold};
}}

QLabel[class="status-error"] {{
    color: {color_status_error};
    font-weight: {font_weight_bold};
}}

/* ── 按钮 ──────────────────────────────────────────────── */
QPushButton {{
    background: {color_bg_card};
    border: 1px solid {color_border};
    border-radius: {radius_md};
    padding: {spacing_sm} {spacing_lg};
    min-height: {button_height_md};
    font-family: {font_family};
    font-size: {font_size_base};
    color: {color_text_primary};
}}

QPushButton:hover {{
    background: {color_bg_hover};
    border-color: {color_border_focus};
}}

QPushButton:pressed {{
    background: {color_primary_light};
}}

QPushButton:disabled {{
    background: {color_bg_hover};
    color: {color_text_muted};
    border-color: {color_border_light};
}}

QPushButton[class="primary"] {{
    background: {color_primary};
    color: {color_text_on_primary};
    border: 1px solid {color_primary_hover};
    border-radius: {radius_xl};
    font-weight: {font_weight_semi};
    min-height: {button_height_lg};
}}

QPushButton[class="primary"]:hover {{
    background: {color_primary_hover};
}}

QPushButton[class="primary"]:pressed {{
    background: {color_primary_pressed};
}}

QPushButton[class="highlight"] {{
    background: {color_highlight};
    color: {color_text_on_highlight};
    border: 1px solid {color_highlight_hover};
    border-radius: {radius_xl};
    font-weight: {font_weight_semi};
}}

QPushButton[class="highlight"]:hover {{
    background: {color_highlight_hover};
}}

QPushButton[class="secondary"] {{
    background: {color_secondary_light};
    color: {color_text_primary};
    border: 1px solid {color_secondary};
    border-radius: {radius_md};
}}

QPushButton[class="small"] {{
    min-height: {button_height_sm};
    max-height: {button_height_sm};
    padding: {spacing_xs} {spacing_md};
    font-size: {font_size_sm};
    border-radius: {radius_sm};
}}

QPushButton[class="pill"] {{
    border-radius: {radius_pill};
    padding: {spacing_xs} {spacing_md};
    min-height: {button_height_sm};
    font-size: {font_size_xs};
}}

QPushButton[class="toggle-btn"] {{
    text-align: left;
    padding: {spacing_sm} {spacing_lg};
    background: {color_bg_hover};
    border: 1px solid {color_border_light};
    border-radius: {radius_sm};
    font-weight: {font_weight_semi};
}}

QPushButton[class="toggle-btn"]:hover {{
    background: {color_bg_selected};
}}

/* ── 输入框 ────────────────────────────────────────────── */
QPlainTextEdit, QTextEdit, QLineEdit {{
    background: {color_bg_input};
    border: 1px solid {color_border};
    border-radius: {radius_md};
    padding: {spacing_sm} {spacing_md};
    font-family: {font_family};
    font-size: {font_size_base};
    color: {color_text_primary};
    selection-background-color: {color_primary_light};
    selection-color: {color_text_primary};
}}

QPlainTextEdit:focus, QTextEdit:focus, QLineEdit:focus {{
    border-color: {color_border_focus};
}}

QPlainTextEdit:disabled, QTextEdit:disabled, QLineEdit:disabled {{
    background: {color_bg_hover};
    color: {color_text_muted};
}}

/* ── 列表 ──────────────────────────────────────────────── */
QListWidget {{
    background: {color_bg_card};
    border: 1px solid {color_border};
    border-radius: {radius_md};
    padding: {spacing_xs};
    font-family: {font_family};
    font-size: {font_size_base};
    color: {color_text_primary};
    outline: none;
}}

QListWidget::item {{
    padding: {spacing_sm} {spacing_md};
    border-radius: {radius_sm};
}}

QListWidget::item:hover {{
    background: {color_bg_hover};
}}

QListWidget::item:selected {{
    background: {color_bg_selected};
    color: {color_text_primary};
}}

/* ── 分组框 ────────────────────────────────────────────── */
QGroupBox {{
    background: {color_bg_card};
    border: 1px solid {color_border};
    border-radius: {radius_lg};
    margin-top: {spacing_xl};
    padding: {spacing_xl} {spacing_lg} {spacing_lg} {spacing_lg};
    font-weight: {font_weight_bold};
    font-size: {font_size_md};
    color: {color_text_primary};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: {spacing_xs} {spacing_md};
    background: {color_bg_card};
    border-radius: {radius_sm} {radius_sm} {radius_none} {radius_none};
}}

/* ── 表格 ──────────────────────────────────────────────── */
QTableWidget {{
    background: {color_bg_card};
    border: 1px solid {color_border};
    border-radius: {radius_md};
    gridline-color: {color_border_light};
    font-family: {font_family};
    font-size: {font_size_base};
    color: {color_text_primary};
    selection-background-color: {color_bg_selected};
    selection-color: {color_text_primary};
}}

QTableWidget::item {{
    padding: {spacing_xs} {spacing_sm};
}}

QTableWidget::item:hover {{
    background: {color_bg_hover};
}}

QHeaderView::section {{
    background: {color_bg_panel};
    border: none;
    border-bottom: 2px solid {color_primary};
    padding: {spacing_sm} {spacing_md};
    font-weight: {font_weight_bold};
    font-size: {font_size_sm};
    color: {color_text_primary};
}}

/* ── 进度条 ────────────────────────────────────────────── */
QProgressBar {{
    background: {color_bg_hover};
    border: 1px solid {color_border};
    border-radius: {radius_pill};
    height: 18px;
    text-align: center;
    font-size: {font_size_xs};
    color: {color_text_primary};
}}

QProgressBar::chunk {{
    background: {color_primary};
    border-radius: {radius_pill};
}}

/* ── 滚动条 ────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {color_bg_window};
    width: 8px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background: {color_border};
    min-height: 30px;
    border-radius: {radius_pill};
}}

QScrollBar::handle:vertical:hover {{
    background: {color_text_muted};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background: {color_bg_window};
    height: 8px;
    margin: 0px;
}}

QScrollBar::handle:horizontal {{
    background: {color_border};
    min-width: 30px;
    border-radius: {radius_pill};
}}

QScrollBar::handle:horizontal:hover {{
    background: {color_text_muted};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ── 菜单 ──────────────────────────────────────────────── */
QMenuBar {{
    background: {color_bg_panel};
    border-bottom: 1px solid {color_border_light};
    font-size: {font_size_base};
    color: {color_text_primary};
    padding: {spacing_xs};
}}

QMenuBar::item {{
    padding: {spacing_sm} {spacing_lg};
    border-radius: {radius_sm};
}}

QMenuBar::item:hover, QMenuBar::item:selected {{
    background: {color_bg_hover};
}}

QMenu {{
    background: {color_bg_card};
    border: 1px solid {color_border};
    border-radius: {radius_md};
    padding: {spacing_xs};
}}

QMenu::item {{
    padding: {spacing_sm} {spacing_xl};
    border-radius: {radius_sm};
}}

QMenu::item:hover, QMenu::item:selected {{
    background: {color_bg_selected};
}}

QMenu::separator {{
    height: 1px;
    background: {color_border_light};
    margin: {spacing_xs} {spacing_md};
}}

/* ── 状态栏 ────────────────────────────────────────────── */
QStatusBar {{
    background: {color_bg_status_bar};
    border-top: 1px solid {color_border_light};
    font-size: {font_size_sm};
    color: {color_text_secondary};
    padding: {spacing_xs} {spacing_md};
}}

/* ── Splitter ──────────────────────────────────────────── */
QSplitter::handle {{
    background: {color_border_light};
}}

QSplitter::handle:hover {{
    background: {color_primary};
}}

/* ── 分隔线 ────────────────────────────────────────────── */
QFrame[frameShape="4"] /* HLine */ {{
    background: {color_border_light};
    max-height: 1px;
    border: none;
}}

QFrame[frameShape="5"] /* VLine */ {{
    background: {color_border_light};
    max-width: 1px;
    border: none;
}}

/* ── 下拉框 ────────────────────────────────────────────── */
QComboBox {{
    background: {color_bg_input};
    border: 1px solid {color_border};
    border-radius: {radius_md};
    padding: {spacing_sm} {spacing_md};
    min-height: {button_height_md};
    font-family: {font_family};
    font-size: {font_size_base};
    color: {color_text_primary};
}}

QComboBox:hover {{
    border-color: {color_border_focus};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background: {color_bg_card};
    border: 1px solid {color_border};
    selection-background-color: {color_bg_selected};
}}

/* ── SpinBox ────────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {{
    background: {color_bg_input};
    border: 1px solid {color_border};
    border-radius: {radius_md};
    padding: {spacing_sm} {spacing_md};
    min-height: {button_height_md};
    font-family: {font_family};
    font-size: {font_size_base};
    color: {color_text_primary};
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {color_border_focus};
}}

/* ── CheckBox ────────────────────────────────────────────── */
QCheckBox {{
    font-family: {font_family};
    font-size: {font_size_base};
    color: {color_text_primary};
    spacing: {spacing_md};
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: {radius_sm};
    border: 2px solid {color_border};
    background: {color_bg_input};
}}

QCheckBox::indicator:checked {{
    background: {color_primary};
    border-color: {color_primary};
}}

QCheckBox::indicator:hover {{
    border-color: {color_border_focus};
}}

/* ── RadioButton ────────────────────────────────────────── */
QRadioButton {{
    font-family: {font_family};
    font-size: {font_size_base};
    color: {color_text_primary};
    spacing: {spacing_md};
}}

QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border-radius: {radius_pill};
    border: 2px solid {color_border};
    background: {color_bg_input};
}}

QRadioButton::indicator:checked {{
    background: {color_primary};
    border-color: {color_primary};
}}

QRadioButton::indicator:hover {{
    border-color: {color_border_focus};
}}

/* ── ScrollArea ────────────────────────────────────────── */
QScrollArea {{
    background: {color_bg_window};
    border: none;
}}

/* ── TabWidget（预留） ─────────────────────────────────── */
QTabWidget::pane {{
    background: {color_bg_card};
    border: 1px solid {color_border};
    border-radius: {radius_md};
}}

QTabBar::tab {{
    background: {color_bg_panel};
    border: 1px solid {color_border};
    border-bottom: none;
    border-radius: {radius_sm} {radius_sm} {radius_none} {radius_none};
    padding: {spacing_sm} {spacing_xl};
    font-size: {font_size_base};
    color: {color_text_secondary};
}}

QTabBar::tab:hover {{
    background: {color_bg_hover};
}}

QTabBar::tab:selected {{
    background: {color_bg_card};
    color: {color_text_primary};
    font-weight: {font_weight_bold};
}}

/* ── ToolTip ────────────────────────────────────────────── */
QToolTip {{
    background: {color_bg_card};
    border: 1px solid {color_border};
    border-radius: {radius_sm};
    padding: {spacing_xs} {spacing_sm};
    font-size: {font_size_sm};
    color: {color_text_primary};
}}

/* ── DialogButtonBox ────────────────────────────────────── */
QDialogButtonBox QPushButton {{
    min-width: 80px;
}}

/* ── Left Panel ────────────────────────────────────────── */
QWidget[class="sidebar"] {{
    background: {color_bg_panel};
    border-right: 1px solid {color_border_light};
}}

QWidget[class="lang-selector"] {{
    background: {color_secondary_light};
    border-radius: {radius_md};
    padding: {spacing_md};
}}

QWidget[class="assets-panel"] {{
    background: {color_primary_light};
    border-radius: {radius_md};
    padding: {spacing_md};
}}
"""
    return qss.strip().format(**tokens.__dict__)


# ---------------------------------------------------------------------------
# ThemeManager：全局单例
# ---------------------------------------------------------------------------

class ThemeManager:
    """全局主题管理器。

    用法：
      tm = theme_manager
      tm.apply(app)               # 应用当前主题
      tm.switch_theme("dark_mode")# 切换主题（自动重新 apply）
      tm.token("color.primary")   # 获取单个 token 值
    """

    def __init__(self) -> None:
        self._themes: Dict[str, ThemeTokens] = {}
        self._current_name: str = "macaron_purple"
        self._app: Optional[QApplication] = None

        # 注册内置主题
        self._register_builtin_themes()

    def _register_builtin_themes(self) -> None:
        self._themes["macaron_purple"] = _macaron_purple_theme()
        self._themes["dark_mode"] = _dark_mode_theme()

    # ── 注册自定义主题 ──────────────────────────────────────

    def register_theme(self, name: str, tokens: ThemeTokens) -> None:
        """注册新主题（后续扩展皮肤只需调此方法）。"""
        self._themes[name] = tokens

    def available_themes(self) -> List[str]:
        """返回所有可用主题名称列表。"""
        return list(self._themes.keys())

    # ── 切换主题 ──────────────────────────────────────────────

    def switch_theme(self, name: str) -> None:
        """切换当前主题并重新应用。"""
        if name not in self._themes:
            raise ValueError(f"未知主题: {name}，可选: {self.available_themes()}")
        self._current_name = name
        if self._app is not None:
            self.apply(self._app)

    def current_theme_name(self) -> str:
        return self._current_name

    def available_theme_names(self) -> list[str]:
        """返回所有已注册主题的名称列表（按注册顺序）。"""
        return list(self._themes.keys())

    # ── 获取 token ────────────────────────────────────────────

    def tokens(self) -> ThemeTokens:
        """返回当前主题的完整 token 对象。"""
        return self._themes[self._current_name]

    def token(self, name: str) -> str:
        """按名称获取单个 token 值。

        例: token("color.primary") → "#B39DDB"
        """
        t = self.tokens()
        return getattr(t, name, "")

    # ── 生成与应用 QSS ───────────────────────────────────────

    def generate_qss(self) -> str:
        """根据当前主题生成完整 QSS 样式表。

        PyQt5 的 QSS 对 [class="xxx"] 动态属性选择器支持不稳定，
        因此在生成后自动为每个 class 选择器添加 #cls_xxx ID 选择器
        作为备用（组件需同时调用 setObjectName("cls_xxx")）。
        """
        raw = _generate_qss(self.tokens())
        # 为每个 [class="xxx"] 选择器追加 #cls_xxx 复本
        import re as _re
        def _dup_class_block(m):
            widget = m.group(1)      # e.g. QWidget, QPushButton, QLabel
            cls_val = m.group(2)     # e.g. sidebar, primary, title
            pseudo = m.group(3)      # e.g. :hover, :pressed, or ""
            body = m.group(4)        # the CSS body content (inside { })
            obj_id = "cls_" + cls_val.replace("-", "_")
            # Return original + duplicate with #cls_xxx selector
            original = m.group(0)
            duplicate = widget + "#" + obj_id + pseudo + " {\n" + body + "\n}"
            return original + "\n" + duplicate

        pattern = _re.compile(
            r'(\w+)\[class="([^"]+)"\]([\s:]*\w*)\s*\{([^}]+)\}',
            _re.DOTALL,
        )
        enhanced = pattern.sub(_dup_class_block, raw)
        return enhanced

    def apply(self, app: QApplication) -> None:
        """将当前主题的 QSS 应用到 QApplication。"""
        self._app = app
        app.setStyleSheet(self.generate_qss())

    # ── 快捷样式片段（供组件局部使用）──────────────────────────

    def status_color(self, status: str) -> str:
        """根据状态字符串返回对应颜色 token。"""
        mapping = {
            "ok": self.token("color_status_ok"),
            "missing": self.token("color_status_missing"),
            "error": self.token("color_status_error"),
        }
        return mapping.get(status, self.token("color_text_muted"))

    def inline_style(self, **kwargs: str) -> str:
        """生成内联样式字符串，所有值从 token 取。

        例: inline_style(font_weight="bold", color="color.text_primary")
        → "font-weight: bold; color: #2D2D2D;"
        """
        parts: list[str] = []
        for css_prop, token_name in kwargs.items():
            # 如果 token_name 是 token 路径（含 .），自动转换
            attr_name = token_name.replace(".", "_")
            value = getattr(self.tokens(), attr_name, token_name)
            # css_prop 中 _ → -
            css_key = css_prop.replace("_", "-")
            parts.append(f"{css_key}: {value}")
        return "; ".join(parts) + ";"


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

theme_manager = ThemeManager()


# ---------------------------------------------------------------------------
# 向后兼容：保留旧 UITheme 接口（逐步迁移）
# ---------------------------------------------------------------------------

class UITheme:
    """旧接口兼容层——指向 theme_manager 的当前 token。

    新代码请直接使用 theme_manager。
    """
    @staticmethod
    def _t() -> ThemeTokens:
        return theme_manager.tokens()

    STATUS_OK_COLOR = property(lambda self: theme_manager.token("color_status_ok"))
    STATUS_MISSING_COLOR = property(lambda self: theme_manager.token("color_status_missing"))
    STATUS_ERROR_COLOR = property(lambda self: theme_manager.token("color_status_error"))

    # 静态兼容（供旧代码直接 UITheme.STATUS_OK_COLOR 访问）
    STATUS_OK_COLOR: str = "#2e7d32"      # 默认值，运行时由 theme 覆盖
    STATUS_MISSING_COLOR: str = "#757575"
    STATUS_ERROR_COLOR: str = "#c62828"

    FONT_FAMILY: str | None = None
    BASE_FONT_POINT_SIZE: int | None = None
    ICON_THEME_PREFIX: str | None = None
    BUTTON_ACCENT_BG: str | None = None
    AI_STATUS_PREFIX: str | None = None

    @classmethod
    def sync_from_manager(cls) -> None:
        """将 theme_manager 当前值同步到类属性（供旧代码使用）。"""
        t = theme_manager.tokens()
        cls.STATUS_OK_COLOR = t.color_status_ok
        cls.STATUS_MISSING_COLOR = t.color_status_missing
        cls.STATUS_ERROR_COLOR = t.color_status_error
        cls.FONT_FAMILY = t.font_family