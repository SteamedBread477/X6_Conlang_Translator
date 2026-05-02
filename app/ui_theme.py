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

import re as _re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from PyQt5.QtWidgets import QApplication


# ---------------------------------------------------------------------------
# Token 定义：设计变量的语义名称
# ---------------------------------------------------------------------------

@dataclass
class ThemeTokens:
    """所有可配置的设计 token，语义命名，与具体皮肤解耦。"""

    # ── 颜色 ──────────────────────────────────────────────────
    # 主色系（紫）
    color_primary: str = "#9B94F2"           # 主色（马卡龙紫）
    color_primary_hover: str = "#9188F1"     # 主色悬停（深紫）
    color_primary_pressed: str = "#7D75E8"   # 主色按下（更深紫）
    color_primary_light: str = "#CDC7F5"     # 主色浅色（浅紫，面板/选中态）
    color_primary_text: str = "#FFFFFF"       # 主色上的文字颜色

    # 辅色系（功能绿）
    color_secondary: str = "#DBF880"          # 辅色（功能绿）
    color_secondary_hover: str = "#B8E560"    # 辅色悬停（深绿）
    color_secondary_light: str = "#F0FBD0"    # 辅色浅色（极浅绿，语言选择区背景）

    # 强调色（=功能绿，统一为绿色系）
    color_highlight: str = "#DBF880"          # 强调色（导入按钮、功能操作）
    color_highlight_hover: str = "#B8E560"    # 强调色悬停

    # 背景色（紫调灰系）
    color_bg_window: str = "#F0EAFA"          # 整体窗体背景（浅紫灰，衬托白色工作区）
    color_bg_panel: str = "#F0EAFA"           # 左侧面板背景（同窗体底色）
    color_bg_card: str = "#FFFFFF"            # 卡片/分组框背景（纯白，叠在浅紫底上产生立体感）
    color_bg_input: str = "#FFFFFF"           # 输入框背景（默认白色）
    color_bg_input_jelly: str = "#F4EDFA"     # 输入框紫果冻背景（极浅紫罗兰填充）
    color_bg_hover: str = "#CDC7F5"           # 通用悬停背景（=浅紫）
    color_bg_selected: str = "#CDC7F5"        # 选中行背景（=浅紫）
    color_bg_status_bar: str = "#CDC7F5"      # 状态栏背景（=浅紫）

    # iOS 分段控制器（Tab）色
    color_tab_selected_bg: str = "#FFFFFF"    # 选中 Tab 背景（纯白+阴影）
    color_tab_unselected_bg: str = "#EDEDED"  # 未选中 Tab 背景（极淡灰）
    color_tab_selected_text: str = "#3D3A4E"  # 选中 Tab 文字（紫灰深色+加粗）
    color_tab_unselected_text: str = "#9A97AE" # 未选中 Tab 文字（紫灰浅色）

    # 绿色按钮色（功能操作）
    color_green_btn_bg: str = "#DBF880"       # 绿色按钮背景（=功能绿）
    color_green_btn_text: str = "#3D3A4E"     # 绿色按钮文字（紫灰深色）
    color_green_btn_hover: str = "#B8E560"    # 绿色按钮悬停（深绿）

    # 文字色（紫灰调）
    color_text_primary: str = "#3D3A4E"       # 主要文字（紫灰调深色）
    color_text_secondary: str = "#6B6880"     # 辅助文字（紫灰调中灰）
    color_text_muted: str = "#9A97AE"          # 次要/提示文字（紫灰调浅灰）
    color_text_on_primary: str = "#FFFFFF"    # 主色按钮上的文字（白）
    color_text_on_highlight: str = "#3D3A4E"  # 强调色上的文字（紫灰深色）

    # 边框色（紫灰调）
    color_border: str = "#D8D5E5"             # 通用边框（紫灰调）
    color_border_focus: str = "#9B94F2"       # 聚焦边框（=主紫）
    color_border_light: str = "#CDC7F5"       # 轻边框（=浅紫，分隔线）

    # 状态色
    color_status_ok: str = "#2e7d32"          # ✓ 成功状态
    color_status_missing: str = "#757575"     # ○ 缺失状态
    color_status_error: str = "#c62828"       # ✗ 锗误状态
    color_status_warning: str = "#cc0000"     # 警告
    color_status_info: str = "#0066cc"        # 信息链接

    # ── 字体 ──────────────────────────────────────────────────
    font_family: str = "Noto Sans SC, Quicksand, HarmonyOS Sans SC, Microsoft YaHei UI, Segoe UI, sans-serif"
    font_size_xs: str = "13px"                # 极小（辅助标注）
    font_size_sm: str = "14px"                # 小（统计、提示）
    font_size_base: str = "15px"              # 基础（正文）
    font_size_md: str = "17px"                # 中（标题）
    font_size_lg: str = "20px"                # 大（对话框标题）
    font_size_xl: str = "24px"                # 极大（窗口标题）
    font_weight_normal: str = "normal"
    font_weight_bold: str = "bold"
    font_weight_semi: str = "600"

    # ── 圆角 ──────────────────────────────────────────────────
    radius_none: str = "0px"
    radius_sm: str = "4px"                    # 小圆角（标签、小按钮）
    radius_md: str = "8px"                    # 中圆角（卡片、输入框）
    radius_lg: str = "12px"                   # 大圆角（面板、对话框）
    radius_xl: str = "16px"                   # 极大圆角（主按钮）
    radius_card: str = "24px"                 # 马卡龙大卡片圆角
    radius_card_lg: str = "32px"              # 超大卡片/面板圆角
    radius_ios: str = "24px"                  # iOS 极简大圆角（卡片、胶囊按钮，升级到24px）
    radius_jelly: str = "20px"                # 紫果冻文本框圆角（升级到20px）
    radius_pill: str = "17px"                  # 药丸形/胶囊按钮（= button_height_sm/2，PyQt5 不支持9999px）
    radius_bar: str = "12px"                  # 进度条圆角（= progress bar height/2）
    radius_scroll: str = "4px"               # 滚动条圆角（= scrollbar width/2）

    # ── 阴影 ──────────────────────────────────────────────────
    shadow_none: str = "none"
    shadow_sm: str = "0 1px 2px rgba(0,0,0,0.06)"
    shadow_md: str = "0 2px 8px rgba(0,0,0,0.10)"
    shadow_lg: str = "0 4px 16px rgba(0,0,0,0.14)"
    shadow_focus: str = "0 0 0 3px rgba(155,148,242,0.3)"
    shadow_ios: str = "0 4px 20px rgba(0,0,0,0.03)"   # iOS 极弱弥散阴影

    # ── 间距 ──────────────────────────────────────────────────
    spacing_xs: str = "5px"
    spacing_sm: str = "8px"
    spacing_md: str = "10px"
    spacing_lg: str = "16px"
    spacing_xl: str = "20px"
    spacing_ios: str = "24px"                # iOS 模块间距（呼吸感）
    spacing_xxl: str = "32px"

    # ── 尺寸 ──────────────────────────────────────────────────
    button_height_sm: str = "34px"
    button_height_md: str = "44px"
    button_height_lg: str = "54px"
    input_min_height: str = "80px"
    panel_min_width: str = "260px"
    sidebar_width: str = "280px"

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
    """暗色主题：紫色和绿色保持原色，白色系变为深紫灰。"""
    return ThemeTokens(
        # 紫色系 — 保持原色
        color_primary="#9B94F2",
        color_primary_hover="#9188F1",
        color_primary_pressed="#7D75E8",
        color_primary_light="#3A3550",
        color_primary_text="#FFFFFF",
        # 绿色系 — 保持原色
        color_secondary="#DBF880",
        color_secondary_hover="#B8E560",
        color_secondary_light="#1A2A1A",
        color_highlight="#DBF880",
        color_highlight_hover="#B8E560",
        # 白色系 → 深紫灰
        color_bg_window="#1A1528",
        color_bg_panel="#1A1528",
        color_bg_card="#2A2440",
        color_bg_input="#2A2440",
        color_bg_input_jelly="#252040",
        color_bg_hover="#3A3550",
        color_bg_selected="#3A3550",
        color_bg_status_bar="#2A2440",
        # Tab — 深紫灰
        color_tab_selected_bg="#2A2440",
        color_tab_unselected_bg="#1A1528",
        color_tab_selected_text="#E8E4F2",
        color_tab_unselected_text="#7A7694",
        # 绿色按钮 — 保持原色
        color_green_btn_bg="#DBF880",
        color_green_btn_text="#3D3A4E",
        color_green_btn_hover="#B8E560",
        # 文字 — 浅紫灰
        color_text_primary="#E8E4F2",
        color_text_secondary="#B0ACCA",
        color_text_muted="#7A7694",
        color_text_on_primary="#FFFFFF",
        color_text_on_highlight="#3D3A4E",
        # 边框 — 深紫灰
        color_border="#3A3550",
        color_border_focus="#9B94F2",
        color_border_light="#3A3550",
        # 状态色
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

QLabel[class="section-title"] {{
    font-weight: {font_weight_bold};
    font-size: {font_size_lg};
    color: {color_text_primary};
}}

QLabel[class="muted"] {{
    color: {color_text_muted};
    font-size: {font_size_sm};
}}

QLabel[class="secondary"] {{
    color: {color_text_secondary};
    font-size: {font_size_sm};
}}

QLabel[class="font-preview"] {{
    background: {color_bg_input_jelly};
    border: none;
    border-radius: {radius_jelly};
    padding: {spacing_xl};
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
    border: none;
    border-radius: {radius_pill};
    padding: {spacing_sm} {spacing_lg};
    min-height: {button_height_md};
    font-family: {font_family};
    font-size: {font_size_base};
    color: {color_text_primary};
}}

QPushButton:hover {{
    background: {color_bg_hover};
}}

QPushButton:pressed {{
    background: {color_primary_light};
}}

QPushButton:disabled {{
    background: {color_bg_hover};
    color: {color_text_muted};
}}

QPushButton[class="primary"] {{
    background: {color_primary};
    color: {color_text_on_primary};
    border: none;
    border-radius: {radius_pill};
    font-weight: {font_weight_semi};
    min-height: {button_height_lg};
}}

QPushButton[class="primary"]:hover {{
    background: {color_primary_hover};
}}

QPushButton[class="primary"]:pressed {{
    background: {color_primary_pressed};
}}

/* ── 小号主色按钮（主色配色 + small 尺寸，与复制按钮尺寸一致）── */
QPushButton[class="primary-sm"] {{
    background: {color_primary};
    color: {color_text_on_primary};
    border: none;
    min-height: {button_height_sm};
    padding: {spacing_sm} {spacing_lg};
    font-size: {font_size_sm};
    font-weight: {font_weight_semi};
    border-radius: {radius_pill};
}}

QPushButton[class="primary-sm"]:hover {{
    background: {color_primary_hover};
}}

QPushButton[class="primary-sm"]:pressed {{
    background: {color_primary_pressed};
}}

QPushButton[class="highlight"] {{
    background: {color_highlight};
    color: {color_text_on_highlight};
    border: none;
    border-radius: {radius_pill};
    font-weight: {font_weight_semi};
}}

QPushButton[class="highlight"]:hover {{
    background: {color_highlight_hover};
}}

QPushButton[class="secondary"] {{
    background: {color_secondary_light};
    color: {color_text_primary};
    border: none;
    border-radius: {radius_pill};
}}

QPushButton[class="small"] {{
    min-height: {button_height_sm};
    padding: {spacing_sm} {spacing_lg};
    font-size: {font_size_sm};
    border: none;
    border-radius: {radius_pill};
    background: {color_green_btn_bg};
    color: {color_green_btn_text};
}}

QPushButton[class="small"]:hover {{
    background: {color_green_btn_hover};
    color: {color_text_on_primary};
}}

QPushButton[class="small"]:pressed {{
    background: {color_primary_pressed};
    color: {color_text_on_primary};
}}

QPushButton[class="pill"] {{
    border-radius: {radius_pill};
    padding: {spacing_xs} {spacing_md};
    min-height: {button_height_sm};
    font-size: {font_size_xs};
}}

/* ── iOS 极简胶囊按钮 ──────────────────────────────────── */
QPushButton[class="add-btn"] {{
    background: {color_primary_light};
    color: {color_text_primary};
    border: none;
    border-radius: {radius_ios};
    padding: {spacing_sm} {spacing_lg};
    min-height: {button_height_sm};
    font-weight: {font_weight_semi};
    font-size: {font_size_sm};
}}

QPushButton[class="add-btn"]:hover {{
    background: {color_primary};
}}

QPushButton[class="add-btn"]:pressed {{
    background: {color_primary_pressed};
}}

QPushButton[class="import-btn"] {{
    background: {color_highlight};
    color: {color_text_on_highlight};
    border: none;
    border-radius: {radius_ios};
    padding: {spacing_sm} {spacing_lg};
    min-height: {button_height_sm};
    font-weight: {font_weight_semi};
    font-size: {font_size_sm};
}}

QPushButton[class="import-btn"]:hover {{
    background: {color_highlight_hover};
}}

QPushButton[class="import-btn"]:pressed {{
    background: {color_primary_pressed};
}}

/* ── iOS 浅绿色胶囊按钮（批量翻译操作）── */
QPushButton[class="green-btn"] {{
    background: {color_green_btn_bg};
    color: {color_green_btn_text};
    border: none;
    border-radius: {radius_pill};
    padding: {spacing_sm} {spacing_lg};
    min-height: {button_height_sm};
    font-weight: {font_weight_semi};
    font-size: {font_size_sm};
}}

QPushButton[class="green-btn"]:hover {{
    background: {color_green_btn_hover};
    color: {color_text_on_primary};
}}

QPushButton[class="green-btn"]:pressed {{
    background: {color_primary_pressed};
    color: {color_text_on_primary};
}}

/* ── 输入框 ────────────────────────────────────────────── */
QPlainTextEdit, QTextEdit, QLineEdit {{
    background: {color_bg_input_jelly};
    border: none;
    border-radius: {radius_jelly};
    padding: {spacing_xl};
    font-family: {font_family};
    font-size: {font_size_base};
    color: {color_text_primary};
    selection-background-color: {color_primary_light};
    selection-color: {color_text_primary};
}}

QPlainTextEdit:focus, QTextEdit:focus, QLineEdit:focus {{
    background: {color_bg_input_jelly};
}}

QPlainTextEdit:disabled, QTextEdit:disabled, QLineEdit:disabled {{
    background: {color_bg_hover};
    color: {color_text_muted};
}}

/* ── 列表 ──────────────────────────────────────────────── */
QListWidget {{
    background: transparent;
    border: none;
    border-radius: {radius_ios};
    padding: {spacing_xs};
    font-family: {font_family};
    font-size: {font_size_base};
    color: {color_text_primary};
    outline: none;
}}

QListWidget::item {{
    padding: {spacing_md} {spacing_lg};
    border-radius: {radius_md};
}}

QListWidget::item:hover {{
    background: {color_bg_hover};
}}

QListWidget::item:selected {{
    background: {color_primary};
    color: {color_text_primary};
    font-weight: {font_weight_bold};
}}

/* ── 分组框 ────────────────────────────────────────────── */
QGroupBox {{
    background: {color_bg_card};
    border: none;
    border-radius: {radius_card};
    margin-top: {spacing_xxl};
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
    border: none;
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
    background: {color_primary_light};
    border: none;
    border-radius: {radius_bar};
    height: 24px;
    text-align: center;
    font-size: {font_size_xs};
    color: {color_text_primary};
}}

QProgressBar::chunk {{
    background: {color_primary};
    border-radius: {radius_bar};
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
    border-radius: {radius_scroll};
}}

QScrollBar:handle:vertical:hover {{
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
    border-radius: {radius_scroll};
}}

QScrollBar:handle:horizontal:hover {{
    background: {color_text_muted};
}}

QScrollBar:add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ── 菜单 ──────────────────────────────────────────────── */
QMenuBar {{
    background: {color_bg_panel};
    border: none;
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
    border: none;
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
    border: none;
    font-size: {font_size_sm};
    color: {color_text_secondary};
    padding: {spacing_xs} {spacing_md};
}}

/* ── Splitter ──────────────────────────────────────────── */
QSplitter::handle:horizontal {{
    width: 6px;
    background: {color_border_light};
    border-radius: 3px;
}}

QSplitter::handle:vertical {{
    height: 6px;
    background: {color_border_light};
    border-radius: 3px;
}}

QSplitter::handle:hover {{
    background: {color_primary};
    border-radius: 3px;
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
    border: none;
    border-radius: {radius_md};
    padding: {spacing_sm} {spacing_md};
    min-height: {button_height_md};
    font-family: {font_family};
    font-size: {font_size_base};
    color: {color_text_primary};
}}

QComboBox:hover {{
    background: {color_bg_hover};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background: {color_bg_card};
    border: none;
    selection-background-color: {color_bg_selected};
}}

/* ── SpinBox ────────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {{
    background: {color_bg_input};
    border: none;
    border-radius: {radius_md};
    padding: {spacing_sm} {spacing_md};
    min-height: {button_height_md};
    font-family: {font_family};
    font-size: {font_size_base};
    color: {color_text_primary};
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    background: {color_bg_input_jelly};
}}

/* ── Slider ────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {color_primary_light};
    height: 8px;
    border-radius: 4px;
}}

QSlider::handle:horizontal {{
    background: {color_primary};
    width: 20px;
    height: 20px;
    margin: -6px 0;
    border-radius: 10px;
}}

QSlider::handle:horizontal:hover {{
    background: {color_primary_hover};
}}

QSlider::handle:horizontal:pressed {{
    background: {color_primary_pressed};
}}

QSlider::sub-page:horizontal {{
    background: {color_primary};
    border-radius: 4px;
}}

/* ── CheckBox ────────────────────────────────────────────── */
QCheckBox {{
    font-family: {font_family};
    font-size: {font_size_base};
    color: {color_text_primary};
    spacing: {spacing_md};
}}

QCheckBox::indicator {{
    width: 22px;
    height: 22px;
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
    width: 22px;
    height: 22px;
    border-radius: {radius_md};
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

/* ── TabWidget（iOS 分段控制器） ─────────────────────────── */
QTabWidget::pane {{
    background: {color_bg_card};
    border: none;
    border-radius: 0px;
    padding: {spacing_ios};
}}

QTabBar {{
    background: {color_tab_unselected_bg};
    border: none;
    border-radius: 0px;
    padding: 3px;
}}

QTabBar::tab {{
    background: transparent;
    border: none;
    border-radius: 0px;
    padding: {spacing_sm} {spacing_xl};
    font-size: {font_size_base};
    color: {color_tab_unselected_text};
    min-width: 150px;
}}

QTabBar::tab:hover {{
    background: {color_bg_hover};
}}

QTabBar::tab:selected {{
    background: {color_tab_selected_bg};
    color: {color_tab_selected_text};
    font-weight: {font_weight_bold};
}}

/* ── ToolTip ────────────────────────────────────────────── */
QToolTip {{
    background: {color_bg_card};
    border: none;
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
    background: {color_bg_window};
    border: none;
}}

QWidget[class="lang-selector"] {{
    background: {color_secondary_light};
    border: none;
    border-radius: {radius_card_lg};
    padding: {spacing_xl};
}}

QWidget[class="assets-panel"] {{
    background: {color_primary_light};
    border: none;
    border-radius: {radius_card_lg};
    padding: {spacing_xl};
}}

/* ── Right Workspace (iOS 去边框容器) ──────────────────── */
QTabWidget[class="right-tabs"] {{
    background: {color_bg_card};
    border: none;
    border-radius: {radius_card_lg};
}}

/* ── Inner Tabs (翻译页签内部的 单句/批量 子Tab) ─── */
QTabWidget[class="inner-tabs"] {{
    background: #FAF8FD;
    border: none;
    border-radius: 0px;
}}

QTabWidget[class="inner-tabs"]::pane {{
    background: #FAF8FD;
    border: none;
    border-radius: 0px;
    padding: 0px;
}}

QTabWidget[class="inner-tabs"] QTabBar::tab {{
    min-width: 120px;
}}

QTabWidget[class="inner-tabs"] QTabBar::tab:selected {{
    background: #FAF8FD;
}}

/* ── ASK 页签 ────────────────────────────────────────────── */
QGroupBox[class="inner-card"] {{
    background: transparent;
    border: none;
    margin-top: 0;
    padding: 0;
    font-weight: {font_weight_normal};
    font-size: {font_size_base};
    color: {color_text_primary};
}}

QGroupBox[class="inner-card"]::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0;
    background: transparent;
    border-radius: 0;
}}



/* ── ASK 页签 ────────────────────────────────────────────── */
QTextEdit[class="chat-display"] {{
    background: {color_bg_input_jelly};
    border: none;
    border-radius: {radius_jelly};
    padding: {spacing_xl};
    font-size: {font_size_base};
}}

QTextEdit[class="chat-display"]:focus {{
    background: {color_bg_input_jelly};
}}

#cls_ask_input {{
    background: {color_bg_input_jelly};
    border: none;
    border-radius: {radius_jelly};
    font-size: {font_size_base};
    padding: {spacing_xl};
}}

#cls_ask_input:focus {{
    background: {color_bg_input_jelly};
}}

#cls_ask_pending_table {{
    background: {color_bg_card};
    border: none;
    border-radius: {radius_md};
    gridline-color: {color_border_light};
    font-size: {font_size_sm};
}}

#cls_ask_pending_table::item {{
    padding: {spacing_xs} {spacing_sm};
}}

#cls_ask_pending_table::item:selected {{
    background: {color_bg_selected};
}}

#cls_ask_token_circle {{
    background: transparent;
}}
"""
    return qss.strip().format(**tokens.__dict__)


# ---------------------------------------------------------------------------
# ThemeManager：全局单例
# ---------------------------------------------------------------------------

# 字号 token 名称列表（用于全局 scale 缩放）
_FONT_SIZE_TOKENS: List[str] = [
    "font_size_xs", "font_size_sm", "font_size_base",
    "font_size_md", "font_size_lg", "font_size_xl",
]


class ThemeManager:
    """全局主题管理器。

    用法：
      tm = theme_manager
      tm.apply(app)               # 应用当前主题
      tm.switch_theme("dark_mode")# 切换主题（自动重新 apply）
      tm.token("color.primary")   # 获取单个 token 值
      tm.apply_font_override(fs)  # 应用用户字体偏好覆写
    """

    def __init__(self) -> None:
        self._themes: Dict[str, ThemeTokens] = {}
        self._current_name: str = "macaron_purple"
        self._app: Optional[QApplication] = None

        # 字体覆写层：用户偏好叠加在主题 token 之上
        self._font_override: Optional[Dict[str, Any]] = None
        self._original_tokens: Optional[Dict[str, str]] = None  # 見写前备份

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
        """切换当前主题并重新应用。

        切换主题后自动重新叠加字体覆写偏好（若有），
        确保用户字体设置在主题切换时不丢失。
        """
        if name not in self._themes:
            raise ValueError(f"未知主题: {name}，可选: {self.available_themes()}")
        self._current_name = name
        # 清除旧主题的备份，以便下次覆写时从新主题读取原始值
        self._original_tokens = None
        if self._font_override is not None:
            self.apply_font_override(self._font_override)
        elif self._app is not None:
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

    # ── 字体覆写 ──────────────────────────────────────────────

    def apply_font_override(self, font_settings: Dict[str, Any]) -> None:
        """将用户字体偏好叠加到当前主题 token 上，并重新应用 QSS。

        font_settings 结构：
          {
            "family_override": "微软雅黑",  # 空=不覆写
            "size_scale": 1.1,             # 1.0=不缩放
            "size_offsets": {              # 预留偏移微调（UI 未解锁）
              "button": 0, "title": 0, "input": 0
            }
          }

        原始 token 值会被备份，reset_font_override() 可恢复。
        """
        t = self.tokens()

        # 首次覆写前备份原始值
        if self._original_tokens is None:
            self._original_tokens = {
                "font_family": t.font_family,
            }
            for key in _FONT_SIZE_TOKENS:
                self._original_tokens[key] = getattr(t, key)

        # ── 覆写字体族 ──
        family = font_settings.get("family_override", "")
        if family:
            # 用户选的字体排最前，后面保留原有 fallback 链
            original_family = self._original_tokens["font_family"]
            # 去掉 fallback 链中与用户选择相同的字体（避免重复）
            fallbacks = [f.strip() for f in original_family.split(",")]
            fallbacks = [f for f in fallbacks if f.lower() != family.lower()]
            t.font_family = family + ", " + ", ".join(fallbacks)
        else:
            t.font_family = self._original_tokens["font_family"]

        # ── 覆写字号（全局 scale + 偏移预留通道）──
        scale = float(font_settings.get("size_scale", 1.0))
        offsets = font_settings.get("size_offsets", {})

        # 偏移预留映射：哪些 token 受哪个 offset 影响
        # 当前 UI 不解锁偏移，offsets 全为 0，scale 是唯一生效参数
        _OFFSET_MAP = {
            "font_size_xs": None,
            "font_size_sm": None,
            "font_size_base": None,   # base 不受任何 offset（正文基准）
            "font_size_md": "title",
            "font_size_lg": "title",
            "font_size_xl": "title",
        }
        # 按钮字号受 button offset 影响：
        #   QSS 中 QPushButton 用 font_size_base / font_size_sm / font_size_xs
        #   这些 token 同时服务于按钮和非按钮控件，单独偏移按钮需要 QSS 级分离，
        #   目前通过额外 QSS 规则实现（见 generate_qss 中的 button offset 区块）。
        # 输入框字号受 input offset 影响：
        #   QSS 中 QPlainTextEdit/QTextEdit/QLineEdit 用 font_size_base，
        #   同理需要 QSS 级分离。

        for key in _FONT_SIZE_TOKENS:
            original_px_str = self._original_tokens[key]
            original_val = int(_re.sub(r"[^\d]", "", original_px_str))
            offset_key = _OFFSET_MAP.get(key)
            offset = int(offsets.get(offset_key, 0)) if offset_key else 0
            new_val = max(8, round(original_val * scale) + offset)
            setattr(t, key, f"{new_val}px")

        # 记录当前覆写参数
        self._font_override = font_settings

        # 重新应用 QSS
        if self._app is not None:
            self.apply(self._app)

    def reset_font_override(self) -> None:
        """清除字体覆写，恢复主题原始 token 值。"""
        if self._original_tokens is None:
            return
        t = self.tokens()
        t.font_family = self._original_tokens["font_family"]
        for key in _FONT_SIZE_TOKENS:
            setattr(t, key, self._original_tokens[key])
        self._original_tokens = None
        self._font_override = None
        if self._app is not None:
            self.apply(self._app)

    def has_font_override(self) -> bool:
        """是否有活跃的字体覆写。"""
        return self._font_override is not None

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