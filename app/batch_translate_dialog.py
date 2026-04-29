"""
批量翻译设置对话框（阶段八）。

在开始翻译前弹出，让用户选择：
  - 翻译模式：规则翻译 / 混合翻译 / AI翻译
  - PaperHub AI 设置（模型、思考模式、自动添加新词、导出报告）
  - 并发设置（并发请求数、请求间隔）

公开接口：
  BatchTranslateSettings — 设置数据结构
  BatchTranslateDialog(settings, parent) -> QDialog
  dialog.get_settings() -> BatchTranslateSettings
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.paperhub_settings import PAPERHUB_MODELS


@dataclass
class BatchTranslateSettings:
    """批量翻译设置。"""
    # 翻译模式：rule / hybrid / ai
    mode: str = "rule"

    # PaperHub AI 设置（hybrid / ai 模式生效）
    model: str = "qwen3-max"
    reasoning_enabled: bool = True
    auto_add_new_words: bool = True
    export_unmatched_report: bool = True

    # 并发设置
    concurrency: int = 3
    request_interval: float = 0.5


# 内置模型列表（与 PaperHub 设置一致）
_BUILTIN_MODEL_IDS: List[str] = [m[1] for m in PAPERHUB_MODELS]


class BatchTranslateDialog(QDialog):
    """批量翻译设置对话框（阶段八）。"""

    def __init__(
        self,
        current_settings: Optional[BatchTranslateSettings] = None,
        paperhub_settings: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._initial = current_settings or BatchTranslateSettings()
        self._paperhub_settings = paperhub_settings or {}

        self.setWindowTitle("批量翻译设置")
        self.setMinimumWidth(480)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── 翻译模式 ──────────────────────────────────────────────
        mode_grp = QGroupBox("翻译模式")
        mode_layout = QVBoxLayout(mode_grp)

        self._btn_rule = QRadioButton("规则翻译（仅使用词库，速度最快）")
        self._btn_hybrid = QRadioButton("混合翻译（词库优先，未匹配词使用 PaperHub AI）")
        self._btn_ai = QRadioButton("AI 翻译（全部使用 PaperHub AI，质量最高但较慢）")

        self._mode_btn_group = QButtonGroup(self)
        self._mode_btn_group.addButton(self._btn_rule, 0)
        self._mode_btn_group.addButton(self._btn_hybrid, 1)
        self._mode_btn_group.addButton(self._btn_ai, 2)

        # 初始选中
        if self._initial.mode == "rule":
            self._btn_rule.setChecked(True)
        elif self._initial.mode == "hybrid":
            self._btn_hybrid.setChecked(True)
        else:
            self._btn_ai.setChecked(True)

        mode_layout.addWidget(self._btn_rule)
        mode_layout.addWidget(self._btn_hybrid)
        mode_layout.addWidget(self._btn_ai)
        layout.addWidget(mode_grp)

        # ── PaperHub AI 设置 ──────────────────────────────────────
        self._ai_grp = QGroupBox("PaperHub AI 设置（选择混合或AI翻译时）")
        ai_layout = QVBoxLayout(self._ai_grp)

        # 模型选择行
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("模型："))
        self._model_combo = QComboBox()
        for display, model_id, desc in PAPERHUB_MODELS:
            self._model_combo.addItem(display, model_id)
        # 如果当前设置中的模型不在内置列表中，追加
        current_model = self._initial.model
        found = False
        for i in range(self._model_combo.count()):
            if self._model_combo.itemData(i) == current_model:
                self._model_combo.setCurrentIndex(i)
                found = True
                break
        if not found and current_model:
            self._model_combo.addItem(current_model, current_model)
            self._model_combo.setCurrentIndex(self._model_combo.count() - 1)
        model_row.addWidget(self._model_combo, 1)
        ai_layout.addLayout(model_row)

        # 复选框行
        self._chk_reasoning = QCheckBox("开启思考模式")
        self._chk_reasoning.setChecked(self._initial.reasoning_enabled)
        ai_layout.addWidget(self._chk_reasoning)

        self._chk_auto_add = QCheckBox("自动将新创词汇添加到词库")
        self._chk_auto_add.setChecked(self._initial.auto_add_new_words)
        ai_layout.addWidget(self._chk_auto_add)

        self._chk_export_report = QCheckBox("翻译完成后导出未匹配词汇报告")
        self._chk_export_report.setChecked(self._initial.export_unmatched_report)
        ai_layout.addWidget(self._chk_export_report)

        layout.addWidget(self._ai_grp)

        # ── 并发设置 ──────────────────────────────────────────────
        conc_grp = QGroupBox("并发设置")
        conc_layout = QVBoxLayout(conc_grp)

        conc_row = QHBoxLayout()
        conc_row.addWidget(QLabel("并发请求数："))
        self._concurrency_spin = QSpinBox()
        self._concurrency_spin.setRange(1, 5)
        self._concurrency_spin.setValue(self._initial.concurrency)
        self._concurrency_spin.setToolTip("AI 翻译时并发请求数，建议 1-5")
        conc_row.addWidget(self._concurrency_spin)
        conc_row.addStretch(1)
        conc_layout.addLayout(conc_row)

        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel("每次请求间隔："))
        self._interval_spin = QDoubleSpinBox()
        self._interval_spin.setRange(0.0, 10.0)
        self._interval_spin.setSingleStep(0.1)
        self._interval_spin.setValue(self._initial.request_interval)
        self._interval_spin.setDecimals(1)
        self._interval_spin.setSuffix(" 秒")
        self._interval_spin.setToolTip("避免触发限流")
        interval_row.addWidget(self._interval_spin)
        interval_row.addStretch(1)
        conc_layout.addLayout(interval_row)

        layout.addWidget(conc_grp)

        layout.addStretch(1)

        # ── 按钮行 ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self._btn_start = QPushButton("开始翻译")
        self._btn_start.setMinimumWidth(100)
        self._btn_start.clicked.connect(self._on_start)
        btn_row.addWidget(self._btn_start)

        btn_cancel = QPushButton("取消")
        btn_cancel.setMinimumWidth(80)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        layout.addLayout(btn_row)

        # ── 初始状态 ──────────────────────────────────────────────
        self._update_ai_group_visibility()
        self._mode_btn_group.buttonClicked.connect(self._update_ai_group_visibility)

    def _update_ai_group_visibility(self) -> None:
        """根据翻译模式切换 AI 设置组的可见性。"""
        is_rule = self._btn_rule.isChecked()
        self._ai_grp.setVisible(not is_rule)

    def _on_start(self) -> None:
        """点击「开始翻译」按钮。"""
        # 如果选择了 AI 或混合模式，检查 PaperHub API Key
        mode = self._get_selected_mode()
        if mode != "rule":
            api_key = str(self._paperhub_settings.get("paperhub_api_key") or "").strip()
            if not api_key:
                msg = (
                    "选择了 AI 或混合翻译模式，但 PaperHub API Key 未配置。\n"
                    "请先在「设置 → PaperHub 设置」中配置 API Key。"
                )
                QMessageBox.warning(self, "缺少 API Key", msg)
                return

        self.accept()

    def _get_selected_mode(self) -> str:
        checked = self._mode_btn_group.checkedId()
        if checked == 0:
            return "rule"
        if checked == 1:
            return "hybrid"
        return "ai"

    def get_settings(self) -> BatchTranslateSettings:
        """获取用户选择的设置。"""
        return BatchTranslateSettings(
            mode=self._get_selected_mode(),
            model=self._model_combo.currentData() or "qwen3-max",
            reasoning_enabled=self._chk_reasoning.isChecked(),
            auto_add_new_words=self._chk_auto_add.isChecked(),
            export_unmatched_report=self._chk_export_report.isChecked(),
            concurrency=self._concurrency_spin.value(),
            request_interval=self._interval_spin.value(),
        )