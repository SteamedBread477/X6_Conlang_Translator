"""
外观与主题设置对话框。

菜单入口：设置 → 外观与主题…

功能（第一版）：
  - 主题切换：下拉选择已注册的主题，实时预览并应用
  - 字体选择：预留接口，后续版本开放自定义字体配置

接口预留：
  - ThemeManager.register_theme() — 注册新主题
  - ThemeManager.switch_theme() — 切换并刷新全局 QSS
  - ThemeTokens.font_family — 字体 token，后续可独立配置
  - ThemeTokens.font_size_* — 字号 token，后续可独立配置
"""
from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.ui_theme import theme_manager, UITheme


# ---------------------------------------------------------------------------
# AppearanceDialog
# ---------------------------------------------------------------------------

class AppearanceDialog(QDialog):
    """外观与主题设置对话框（第一版 — 预留字体接口）。

    当前只开放主题切换；字体配置作为 UI 占位，后续版本解锁。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("外观与主题")
        self.setMinimumWidth(420)
        self._init_ui()

    # ── UI 构建 ──────────────────────────────────────────────────────

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)

        # ── 主题选择区 ────────────────────────────────────────────
        theme_group = QGroupBox("主题")
        theme_group.setObjectName("cls_theme_group")
        theme_lay = QVBoxLayout(theme_group)

        # 当前主题提示
        self._current_label = QLabel()
        self._current_label.setObjectName("cls_secondary")
        self._refresh_current_label()
        theme_lay.addWidget(self._current_label)

        # 主题下拉
        self._theme_combo = QComboBox()
        self._theme_combo.setObjectName("cls_theme_combo")
        self._populate_theme_combo()
        theme_lay.addWidget(self._theme_combo)

        root.addWidget(theme_group)

        # ── 字体配置区（预留占位，后续版本解锁）──────────────────
        font_group = QGroupBox("字体（预留 — 后续版本开放）")
        font_group.setObjectName("cls_font_group")
        font_lay = QVBoxLayout(font_group)

        placeholder_text = (
            "自定义字体和字号配置将在后续版本中开放。<br>"
            "当前字体由主题 token 决定（font_family / font_size_*）。"
        )
        placeholder = QLabel(placeholder_text)
        placeholder.setObjectName("cls_muted")
        font_lay.addWidget(placeholder)

        # 预留：字体族选择（暂禁用）
        # self._font_family_combo = QComboBox()
        # self._font_family_combo.setEnabled(False)
        # font_lay.addWidget(self._font_family_combo)

        # 预留：字号调整（暂禁用）
        # self._font_size_slider = QSlider(Qt.Horizontal)
        # self._font_size_slider.setEnabled(False)
        # font_lay.addWidget(self._font_size_slider)

        root.addWidget(font_group)

        # ── 按钮栏 ────────────────────────────────────────────────
        btn_box = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        btn_box.setObjectName("cls_btn_box")
        btn_box.button(QDialogButtonBox.Apply).clicked.connect(self._apply_theme)
        btn_box.button(QDialogButtonBox.Close).clicked.connect(self.reject)
        root.addWidget(btn_box)

    # ── 数据填充 ──────────────────────────────────────────────────────

    def _populate_theme_combo(self) -> None:
        """从 ThemeManager 拉取已注册主题列表，填充下拉框。"""
        self._theme_combo.clear()
        names = theme_manager.available_theme_names()
        current = theme_manager.current_theme_name()
        for name in names:
            label = name.replace("_", " ").title()
            self._theme_combo.addItem(label, name)
        # 选中当前主题
        idx = names.index(current) if current in names else 0
        self._theme_combo.setCurrentIndex(idx)

    def _refresh_current_label(self) -> None:
        """刷新「当前主题」提示文字。"""
        current = theme_manager.current_theme_name()
        label = current.replace("_", " ").title()
        self._current_label.setText("当前主题：" + label)

    # ── 操作 ──────────────────────────────────────────────────────────

    def _apply_theme(self) -> None:
        """应用下拉框中选中的主题。"""
        selected = self._theme_combo.currentData()
        if selected is None:
            return

        # 切换主题
        theme_manager.switch_theme(selected)

        # 同步兼容层
        UITheme.sync_from_manager()

        # 刷新整个应用 QSS
        app = QApplication.instance()
        if app is not None:
            theme_manager.apply(app)
            # 强制刷新所有窗口样式
            for widget in app.topLevelWidgets():
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()

        # 更新提示
        self._refresh_current_label()