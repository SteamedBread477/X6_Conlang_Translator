"""
外观与主题设置对话框。

菜单入口：设置 → 外观与主题…

功能：
  - 主题切换：下拉选择已注册的主题，实时预览并应用
  - 字体族选择：普通 QComboBox 列出系统可缩放字体族（首项=跟随主题默认）
  - 字号缩放：Slider 0.8~1.3，步长 0.05，旁边显示百分比
  - 实时预览：底部 QLabel 用当前字体+字号渲染示例文本

接口：
  - ThemeManager.register_theme() — 注册新主题
  - ThemeManager.switch_theme() — 切换并刷新全局 QSS
  - ThemeManager.apply_font_override() — 字体偏好覆写
  - ThemeManager.reset_font_override() — 清除字体覆写
  - font_settings.load_font_settings() — 读取字体配置
  - font_settings.save_font_settings() — 写入字体配置
"""
from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.ui_theme import theme_manager, UITheme
from app.font_settings import load_font_settings, save_font_settings, DEFAULT_FONT_SETTINGS

# "跟随主题默认"占位项的显示文本
_DEFAULT_FAMILY_LABEL = "跟随主题默认"


# ---------------------------------------------------------------------------
# AppearanceDialog
# ---------------------------------------------------------------------------

class AppearanceDialog(QDialog):
    """外观与主题设置对话框。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("外观与主题")
        self.setMinimumWidth(480)
        self._init_ui()
        self._load_current_settings()

    # ── UI 构建 ──────────────────────────────────────────────────────

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(16)

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

        # ── 字体配置区 ────────────────────────────────────────────
        font_group = QGroupBox("字体")
        font_group.setObjectName("cls_font_group")
        font_lay = QVBoxLayout(font_group)
        font_lay.setSpacing(12)

        # 字体族选择行
        family_row = QHBoxLayout()
        family_label = QLabel("字体族：")
        family_label.setObjectName("cls_secondary")
        family_row.addWidget(family_label)

        self._font_family_combo = QComboBox()
        self._font_family_combo.setObjectName("cls_font_family_combo")
        self._populate_font_family_combo()
        family_row.addWidget(self._font_family_combo, 1)
        font_lay.addLayout(family_row)

        # 字号缩放行
        scale_row = QHBoxLayout()
        scale_label = QLabel("字号缩放：")
        scale_label.setObjectName("cls_secondary")
        scale_row.addWidget(scale_label)

        self._scale_slider = QSlider(Qt.Horizontal)
        self._scale_slider.setObjectName("cls_scale_slider")
        self._scale_slider.setMinimum(80)   # 0.8 → 80
        self._scale_slider.setMaximum(130)  # 1.3 → 130
        self._scale_slider.setSingleStep(5) # 0.05 → 5
        self._scale_slider.setPageStep(10)  # 0.10 → 10
        self._scale_slider.setValue(100)    # 1.0 → 100
        self._scale_slider.setTickPosition(QSlider.TicksBelow)
        self._scale_slider.setTickInterval(10)
        scale_row.addWidget(self._scale_slider, 1)

        self._scale_pct_label = QLabel("100%")
        self._scale_pct_label.setObjectName("cls_secondary")
        self._scale_pct_label.setMinimumWidth(50)
        scale_row.addWidget(self._scale_pct_label)

        font_lay.addLayout(scale_row)

        # 实时预览区
        preview_label_title = QLabel("预览：")
        preview_label_title.setObjectName("cls_secondary")
        font_lay.addWidget(preview_label_title)

        self._preview_label = QLabel(
            "示例文本 Sample — 字体预览 Abc 你好世界 菇蓏葡菇"
        )
        self._preview_label.setObjectName("cls_font_preview")
        self._preview_label.setAlignment(Qt.AlignCenter)
        self._preview_label.setMinimumHeight(60)
        font_lay.addWidget(self._preview_label)

        root.addWidget(font_group)

        # ── 按钮栏 ────────────────────────────────────────────────
        btn_box = QDialogButtonBox(
            QDialogButtonBox.Apply | QDialogButtonBox.RestoreDefaults
            | QDialogButtonBox.Close
        )
        btn_box.setObjectName("cls_btn_box")
        btn_box.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
        btn_box.button(QDialogButtonBox.RestoreDefaults).clicked.connect(
            self._restore_defaults
        )
        btn_box.button(QDialogButtonBox.Close).clicked.connect(self.reject)
        root.addWidget(btn_box)

        # ── 信号连接 ────────────────────────────────────────────────
        self._scale_slider.valueChanged.connect(self._on_scale_changed)
        self._font_family_combo.currentIndexChanged.connect(
            self._on_family_changed
        )

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

    def _populate_font_family_combo(self) -> None:
        """用 QFontDatabase 填充系统可缩放字体族列表。

        首项为占位「跟随主题默认」，后续为系统字体族名称（排序）。
        """
        self._font_family_combo.clear()
        self._font_family_combo.addItem(_DEFAULT_FAMILY_LABEL)  # idx 0 → 默认

        db = QFontDatabase()
        families = sorted(db.families())
        for f in families:
            self._font_family_combo.addItem(f)

    def _refresh_current_label(self) -> None:
        """刷新「当前主题」提示文字。"""
        current = theme_manager.current_theme_name()
        label = current.replace("_", " ").title()
        self._current_label.setText("当前主题：" + label)

    def _load_current_settings(self) -> None:
        """从配置文件加载当前字体设置，填充 UI 控件。"""
        fs = load_font_settings()

        # 字体族
        family = fs.get("family_override", "")
        if family:
            # 在 combo 中找到对应项
            idx = self._font_family_combo.findText(
                family, Qt.MatchExactly | Qt.MatchCaseSensitive
            )
            if idx >= 0:
                self._font_family_combo.setCurrentIndex(idx)
            else:
                # 字体不在系统列表中（可能已卸载），插入到第二位
                self._font_family_combo.insertItem(1, family)
                self._font_family_combo.setCurrentIndex(1)
        else:
            self._font_family_combo.setCurrentIndex(0)  # "跟随主题默认"

        # 字号缩放
        scale = fs.get("size_scale", 1.0)
        self._scale_slider.setValue(int(round(scale * 100)))
        self._update_scale_label()

        # 预览
        self._update_preview()

    # ── 信号处理 ──────────────────────────────────────────────────────

    def _on_scale_changed(self, value: int) -> None:
        """字号滑条变化 → 更新百分比标签 + 预览。"""
        self._update_scale_label()
        self._update_preview()

    def _on_family_changed(self, index: int) -> None:
        """字体族下拉变化 → 更新预览。"""
        self._update_preview()

    def _update_scale_label(self) -> None:
        """更新字号百分比标签。"""
        pct = self._scale_slider.value()
        self._scale_pct_label.setText(f"{pct}%")

    def _update_preview(self) -> None:
        """更新预览标签的字体和字号。"""
        family = self._current_family_override()
        scale = self._scale_slider.value() / 100.0

        font = QFont()
        if family:
            font.setFamily(family)

        # 用缩放后的字号渲染预览
        base_size = 15  # ThemeTokens.font_size_base 默认值
        preview_size = max(8, round(base_size * scale))
        font.setPixelSize(preview_size)
        self._preview_label.setFont(font)

    # ── 辅助 ──────────────────────────────────────────────────────────

    def _current_family_override(self) -> str:
        """获取当前 UI 中选择的字体族（空=跟随主题默认）。"""
        idx = self._font_family_combo.currentIndex()
        if idx == 0:
            return ""  # "跟随主题默认"
        return self._font_family_combo.currentText()

    def _build_font_settings(self) -> dict:
        """从当前 UI 控件状态构建 font_settings dict。"""
        fs = load_font_settings()  # 保留 size_offsets（预留）
        fs["family_override"] = self._current_family_override()
        fs["size_scale"] = self._scale_slider.value() / 100.0
        return fs

    # ── 操作 ──────────────────────────────────────────────────────────

    def _apply(self) -> None:
        """应用当前所有设置（主题 + 字体）。"""
        # ── 主题 ──
        selected = self._theme_combo.currentData()
        if selected is not None:
            theme_manager.switch_theme(selected)
            UITheme.sync_from_manager()

        # ── 字体 ──
        fs = self._build_font_settings()

        # 判断是否需要覆写：family_override 非空 或 size_scale ≠ 1.0
        family = fs.get("family_override", "")
        scale = fs.get("size_scale", 1.0)
        if family or scale != 1.0:
            theme_manager.apply_font_override(fs)
        else:
            theme_manager.reset_font_override()

        # 保存到配置文件
        save_font_settings(fs)

        # 强制刷新所有窗口样式
        app = QApplication.instance()
        if app is not None:
            theme_manager.apply(app)
            for widget in app.topLevelWidgets():
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()

        # 更新提示
        self._refresh_current_label()

    def _restore_defaults(self) -> None:
        """恢复字体设置为默认值（跟随主题）。"""
        # 重置 UI 控件
        self._font_family_combo.setCurrentIndex(0)
        self._scale_slider.setValue(100)

        # 重置覆写
        theme_manager.reset_font_override()

        # 保存默认值到配置文件
        save_font_settings(DEFAULT_FONT_SETTINGS)

        # 强制刷新
        app = QApplication.instance()
        if app is not None:
            theme_manager.apply(app)
            for widget in app.topLevelWidgets():
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()

        self._refresh_current_label()
        self._update_preview()