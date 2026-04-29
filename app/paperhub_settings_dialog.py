"""
PaperHub AI 设置对话框。

菜单入口：设置 → PaperHub 设置

功能：
  - 启用/禁用 AI 辅助翻译开关
  - API Key 输入（密码模式 + 显示/隐藏切换）
  - 服务地址（只读显示）
  - 模型选择（动态从 PaperHub 拉取列表，初始用内置备用列表）
  - AI 使用策略（3 种单选）
  - 高级参数（思考模式、Temperature、Max Tokens）
  - 测试连接（后台线程，不阻塞 UI）
  - 保存 / 取消
  - 底部帮助链接
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtCore import QUrl

from app.paperhub_settings import (
    DEFAULT_PAPERHUB_SETTINGS,
    PAPERHUB_DASHBOARD_URL,
    PAPERHUB_MODELS,
    load_paperhub_settings,
    save_paperhub_settings,
)

# 内置备用模型列表（仅在未能联网拉取时使用）
_BUILTIN_MODEL_IDS: List[str] = [m[1] for m in PAPERHUB_MODELS]


# ---------------------------------------------------------------------------
# 后台线程：测试连接
# ---------------------------------------------------------------------------

class _TestConnectionThread(QThread):
    result_ready = pyqtSignal(bool, str)

    def __init__(self, api_key: str, base_url: str, model: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._api_key = api_key
        self._base_url = base_url
        self._model = model

    def run(self) -> None:
        from app.paperhub_client import test_paperhub_connection
        ok, msg = test_paperhub_connection(self._api_key, self._base_url, self._model)
        self.result_ready.emit(ok, msg)


# ---------------------------------------------------------------------------
# 后台线程：拉取模型列表
# ---------------------------------------------------------------------------

class _FetchModelsThread(QThread):
    """从 PaperHub 异步拉取可用模型列表。"""
    result_ready = pyqtSignal(bool, list, str)   # (success, model_ids, error)

    def __init__(self, api_key: str, base_url: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._api_key = api_key
        self._base_url = base_url

    def run(self) -> None:
        from app.paperhub_client import fetch_paperhub_models
        ok, model_ids, err = fetch_paperhub_models(self._api_key, self._base_url)
        self.result_ready.emit(ok, model_ids, err)


# ---------------------------------------------------------------------------
# 主对话框
# ---------------------------------------------------------------------------

class PaperHubSettingsDialog(QDialog):
    """PaperHub AI 配置对话框。"""

    def __init__(self, data_dir: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._data_dir = data_dir
        self._settings: Dict[str, Any] = load_paperhub_settings(data_dir)
        self._test_thread: Optional[_TestConnectionThread] = None
        self._fetch_thread: Optional[_FetchModelsThread] = None

        self.setWindowTitle("PaperHub AI 设置")
        self.setMinimumWidth(560)
        self.setMinimumHeight(600)

        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # ── 滚动区域 ───────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(10)

        # ── 总开关 ─────────────────────────────────────────────────
        self._enabled_cb = QCheckBox("启用 AI 辅助翻译")
        self._enabled_cb.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._enabled_cb)

        layout.addWidget(_separator())

        # ── API 配置 ───────────────────────────────────────────────
        api_grp = QGroupBox("API 配置")
        api_layout = QVBoxLayout(api_grp)
        api_layout.setSpacing(6)

        api_layout.addWidget(QLabel("PaperHub API Key（llm_api 类型）："))
        key_row = QHBoxLayout()
        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.Password)
        self._api_key_edit.setPlaceholderText("sk-xxxxxxxxxxxxxxxx")
        key_row.addWidget(self._api_key_edit, 1)
        self._toggle_key_btn = QPushButton("显示")
        self._toggle_key_btn.setFixedWidth(52)
        self._toggle_key_btn.setCheckable(True)
        self._toggle_key_btn.toggled.connect(self._toggle_key_visibility)
        key_row.addWidget(self._toggle_key_btn)
        api_layout.addLayout(key_row)

        url_row = QHBoxLayout()
        url_row.addWidget(QLabel("服务地址："))
        self._base_url_lbl = QLabel(DEFAULT_PAPERHUB_SETTINGS["paperhub_base_url"])
        self._base_url_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._base_url_lbl.setStyleSheet("color: #555;")
        url_row.addWidget(self._base_url_lbl, 1)
        api_layout.addLayout(url_row)

        layout.addWidget(api_grp)

        # ── 模型选择（动态） ───────────────────────────────────────
        model_grp = QGroupBox("模型选择")
        model_layout = QVBoxLayout(model_grp)
        model_layout.setSpacing(6)

        combo_row = QHBoxLayout()
        self._model_combo = QComboBox()
        self._model_combo.setMinimumWidth(300)
        self._model_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        combo_row.addWidget(self._model_combo, 1)

        self._fetch_models_btn = QPushButton("刷新模型列表")
        self._fetch_models_btn.setToolTip(
            "从 PaperHub 拉取最新可用模型（需先填写 API Key）"
        )
        self._fetch_models_btn.clicked.connect(self._on_fetch_models)
        combo_row.addWidget(self._fetch_models_btn)
        model_layout.addLayout(combo_row)

        self._model_status_lbl = QLabel(
            f"内置备用列表，共 {len(_BUILTIN_MODEL_IDS)} 个模型。"
            "填写 API Key 后点击「刷新模型列表」获取完整列表。"
        )
        self._model_status_lbl.setStyleSheet("color: #666; font-size: 11px;")
        self._model_status_lbl.setWordWrap(True)
        model_layout.addWidget(self._model_status_lbl)

        layout.addWidget(model_grp)

        # ── AI 使用策略 ────────────────────────────────────────────
        strategy_grp = QGroupBox("AI 使用策略")
        strategy_layout = QVBoxLayout(strategy_grp)
        strategy_layout.setSpacing(4)
        self._strategy_group = QButtonGroup(self)

        strategies = [
            ("unmatched_only", "仅在词汇未匹配时使用 AI（推荐，节约 API 用量）"),
            ("always",         "所有翻译都使用 AI"),
            ("confirm",        "AI 生成候选，用户确认后采用"),
        ]
        for i, (value, label) in enumerate(strategies):
            rb = QRadioButton(label)
            rb.setProperty("strategy_value", value)
            if value == "confirm":
                rb.setToolTip("AI 生成翻译候选后弹出确认对话框，用户可采用、修改后采用或放弃")
            strategy_layout.addWidget(rb)
            self._strategy_group.addButton(rb, i)
        layout.addWidget(strategy_grp)

        # ── 高级参数 ───────────────────────────────────────────────
        adv_grp = QGroupBox("高级参数")
        adv_layout = QVBoxLayout(adv_grp)
        adv_layout.setSpacing(6)

        self._reasoning_cb = QCheckBox("开启思考模式（reasoning.enabled = true）")
        self._reasoning_cb.setToolTip(
            "启用后模型将进行链式推理（Chain-of-Thought），翻译质量更高，但响应稍慢。"
        )
        adv_layout.addWidget(self._reasoning_cb)

        temp_row = QHBoxLayout()
        temp_row.addWidget(QLabel("Temperature（0 – 2）："))
        self._temperature_spin = QDoubleSpinBox()
        self._temperature_spin.setRange(0.0, 2.0)
        self._temperature_spin.setSingleStep(0.1)
        self._temperature_spin.setDecimals(1)
        self._temperature_spin.setFixedWidth(80)
        temp_row.addWidget(self._temperature_spin)
        temp_row.addStretch(1)
        adv_layout.addLayout(temp_row)

        tokens_row = QHBoxLayout()
        tokens_row.addWidget(QLabel("Max Tokens："))
        self._max_tokens_spin = QSpinBox()
        self._max_tokens_spin.setRange(256, 32768)
        self._max_tokens_spin.setSingleStep(256)
        self._max_tokens_spin.setFixedWidth(100)
        tokens_row.addWidget(self._max_tokens_spin)
        tokens_row.addStretch(1)
        adv_layout.addLayout(tokens_row)

        layout.addWidget(adv_grp)

        # ── 测试连接 ───────────────────────────────────────────────
        layout.addWidget(_separator())

        test_row = QHBoxLayout()
        self._test_btn = QPushButton("测试连接")
        self._test_btn.clicked.connect(self._on_test_connection)
        test_row.addWidget(self._test_btn)
        self._test_status_lbl = QLabel("")
        self._test_status_lbl.setWordWrap(True)
        test_row.addWidget(self._test_status_lbl, 1)
        layout.addLayout(test_row)

        layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        # ── 帮助链接 ───────────────────────────────────────────────
        help_lbl = QLabel(
            "API Key 获取方式：PaperHub 工作台 → API Key → 新建 Key → 选择 llm_api 类型"
        )
        help_lbl.setStyleSheet("color: #666; font-size: 11px;")
        help_lbl.setWordWrap(True)
        root.addWidget(help_lbl)

        dashboard_btn = QPushButton("打开 PaperHub 工作台")
        dashboard_btn.setFlat(True)
        dashboard_btn.setStyleSheet("color: #0066cc; text-decoration: underline;")
        dashboard_btn.setCursor(Qt.PointingHandCursor)
        dashboard_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(PAPERHUB_DASHBOARD_URL))
        )
        root.addWidget(dashboard_btn)

        root.addWidget(_separator())

        # ── 保存 / 取消 ───────────────────────────────────────────
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Save).setText("保存")
        btn_box.button(QDialogButtonBox.Cancel).setText("取消")
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

    # ------------------------------------------------------------------
    # 模型下拉填充
    # ------------------------------------------------------------------

    def _populate_model_combo(
        self,
        model_ids: List[str],
        selected: Optional[str] = None,
    ) -> None:
        """用给定 model_ids 重新填充下拉框，尽量保持当前选中项。"""
        current = selected or self._model_combo.currentData() or ""
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        for mid in model_ids:
            self._model_combo.addItem(mid, mid)
        # 尝试恢复之前选中的模型
        idx = self._model_combo.findData(current)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)
        elif model_ids:
            self._model_combo.setCurrentIndex(0)
        self._model_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # 数据加载 / 收集
    # ------------------------------------------------------------------

    def _load_values(self) -> None:
        s = self._settings
        self._enabled_cb.setChecked(bool(s.get("paperhub_enabled")))
        self._api_key_edit.setText(str(s.get("paperhub_api_key") or ""))

        # 填充内置备用列表，选中已保存的模型
        saved_model = str(s.get("paperhub_model") or _BUILTIN_MODEL_IDS[0])
        # 如果保存的模型不在内置列表里，也加进去（避免丢失已选模型）
        initial_ids = list(_BUILTIN_MODEL_IDS)
        if saved_model and saved_model not in initial_ids:
            initial_ids.insert(0, saved_model)
        self._populate_model_combo(initial_ids, selected=saved_model)

        target_strategy = str(s.get("paperhub_strategy") or "unmatched_only")
        for btn in self._strategy_group.buttons():
            if btn.property("strategy_value") == target_strategy:
                btn.setChecked(True)
                break
        else:
            first = self._strategy_group.button(0)
            if first:
                first.setChecked(True)

        self._reasoning_cb.setChecked(bool(s.get("paperhub_reasoning_enabled", True)))
        self._temperature_spin.setValue(float(s.get("paperhub_temperature", 0.7)))
        self._max_tokens_spin.setValue(int(s.get("paperhub_max_tokens", 2048)))

    def _collect_values(self) -> Dict[str, Any]:
        selected_model = (
            self._model_combo.currentData()
            or self._model_combo.currentText()
            or _BUILTIN_MODEL_IDS[0]
        )

        selected_strategy = "unmatched_only"
        for btn in self._strategy_group.buttons():
            if btn.isChecked():
                selected_strategy = btn.property("strategy_value")
                break

        return {
            "paperhub_enabled": self._enabled_cb.isChecked(),
            "paperhub_api_key": self._api_key_edit.text().strip(),
            "paperhub_base_url": DEFAULT_PAPERHUB_SETTINGS["paperhub_base_url"],
            "paperhub_model": selected_model,
            "paperhub_strategy": selected_strategy,
            "paperhub_reasoning_enabled": self._reasoning_cb.isChecked(),
            "paperhub_temperature": self._temperature_spin.value(),
            "paperhub_max_tokens": self._max_tokens_spin.value(),
        }

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def _toggle_key_visibility(self, checked: bool) -> None:
        self._api_key_edit.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password
        )
        self._toggle_key_btn.setText("隐藏" if checked else "显示")

    # ── 拉取模型列表 ────────────────────────────────────────────────

    def _on_fetch_models(self) -> None:
        api_key = self._api_key_edit.text().strip()
        if not api_key:
            self._model_status_lbl.setText("❌ 请先填写 API Key 再刷新。")
            self._model_status_lbl.setStyleSheet("color: #cc0000; font-size: 11px;")
            return

        base_url = DEFAULT_PAPERHUB_SETTINGS["paperhub_base_url"]
        self._fetch_models_btn.setEnabled(False)
        self._fetch_models_btn.setText("获取中…")
        self._model_status_lbl.setText("正在从 PaperHub 拉取模型列表，请稍候…")
        self._model_status_lbl.setStyleSheet("color: #888; font-size: 11px;")

        self._fetch_thread = _FetchModelsThread(api_key, base_url, self)
        self._fetch_thread.result_ready.connect(self._on_fetch_models_result)
        self._fetch_thread.start()

    def _on_fetch_models_result(
        self, ok: bool, model_ids: List[str], err: str
    ) -> None:
        self._fetch_models_btn.setEnabled(True)
        self._fetch_models_btn.setText("刷新模型列表")

        if ok and model_ids:
            self._populate_model_combo(model_ids)
            self._model_status_lbl.setText(
                f"✓ 已获取 {len(model_ids)} 个可用模型。"
            )
            self._model_status_lbl.setStyleSheet("color: #007700; font-size: 11px;")
        else:
            self._model_status_lbl.setText(
                f"✗ 获取失败：{err}\n（当前使用内置备用列表）"
            )
            self._model_status_lbl.setStyleSheet("color: #cc0000; font-size: 11px;")

    # ── 测试连接 ─────────────────────────────────────────────────────

    def _on_test_connection(self) -> None:
        settings = self._collect_values()
        api_key = settings["paperhub_api_key"]
        base_url = settings["paperhub_base_url"]
        model = settings["paperhub_model"]

        if not api_key:
            self._test_status_lbl.setText("❌ 请先填写 API Key")
            self._test_status_lbl.setStyleSheet("color: #cc0000;")
            return

        self._test_btn.setEnabled(False)
        self._test_btn.setText("测试中…")
        self._test_status_lbl.setText("正在连接，请稍候…")
        self._test_status_lbl.setStyleSheet("color: #888;")

        self._test_thread = _TestConnectionThread(api_key, base_url, model, self)
        self._test_thread.result_ready.connect(self._on_test_result)
        self._test_thread.start()

    def _on_test_result(self, ok: bool, message: str) -> None:
        self._test_btn.setEnabled(True)
        self._test_btn.setText("测试连接")
        if ok:
            self._test_status_lbl.setText(f"✓ {message}")
            self._test_status_lbl.setStyleSheet("color: #007700;")
        else:
            self._test_status_lbl.setText(f"✗ {message}")
            self._test_status_lbl.setStyleSheet("color: #cc0000;")

    # ── 保存 ─────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        values = self._collect_values()
        try:
            save_paperhub_settings(self._data_dir, values)
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self._settings = values
        self.accept()

    def settings(self) -> Dict[str, Any]:
        return dict(self._settings)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setFrameShadow(QFrame.Sunken)
    return sep
