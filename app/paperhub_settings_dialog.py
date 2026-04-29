"""
PaperHub AI 设置对话框。

菜单入口：设置 → PaperHub 设置

功能：
  - 启用/禁用 AI 辅助翻译开关
  - API Key 输入（密码模式 + 显示/隐藏切换）
  - 服务地址（只读显示）
  - 模型选择（4 个单选按钮）
  - AI 使用策略（3 种单选）
  - 高级参数（思考模式、Temperature、Max Tokens）
  - 测试连接（后台线程，不阻塞 UI）
  - 保存 / 取消
  - 底部帮助链接
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
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


# ---------------------------------------------------------------------------
# 后台连接测试线程（避免阻塞 UI 主线程）
# ---------------------------------------------------------------------------

class _TestConnectionThread(QThread):
    result_ready = pyqtSignal(bool, str)

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._api_key = api_key
        self._base_url = base_url
        self._model = model

    def run(self) -> None:
        from app.paperhub_client import test_paperhub_connection
        ok, msg = test_paperhub_connection(self._api_key, self._base_url, self._model)
        self.result_ready.emit(ok, msg)


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

        self.setWindowTitle("PaperHub AI 设置")
        self.setMinimumWidth(540)
        self.setMinimumHeight(600)

        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # ── 滚动区域（对话框内容较多，适配小屏） ──────────────────
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

        key_lbl = QLabel("PaperHub API Key（llm_api 类型）：")
        api_layout.addWidget(key_lbl)

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

        # ── 模型选择 ───────────────────────────────────────────────
        model_grp = QGroupBox("推荐模型")
        model_layout = QVBoxLayout(model_grp)
        model_layout.setSpacing(4)
        self._model_group = QButtonGroup(self)
        for i, (display_name, model_id, description) in enumerate(PAPERHUB_MODELS):
            rb = QRadioButton(f"{display_name}（{description}）")
            rb.setProperty("model_id", model_id)
            model_layout.addWidget(rb)
            self._model_group.addButton(rb, i)
        layout.addWidget(model_grp)

        # ── AI 使用策略 ────────────────────────────────────────────
        strategy_grp = QGroupBox("AI 使用策略")
        strategy_layout = QVBoxLayout(strategy_grp)
        strategy_layout.setSpacing(4)
        self._strategy_group = QButtonGroup(self)

        strategies = [
            ("unmatched_only", "仅在词汇未匹配时使用 AI（推荐，节约 API 用量）"),
            ("always",         "所有翻译都使用 AI"),
            ("confirm",        "AI 生成候选，用户确认后采用（预留，即将支持）"),
        ]
        for i, (value, label) in enumerate(strategies):
            rb = QRadioButton(label)
            rb.setProperty("strategy_value", value)
            if value == "confirm":
                rb.setEnabled(False)
                rb.setToolTip("该功能将在后续版本中支持")
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
    # 数据加载 / 收集
    # ------------------------------------------------------------------

    def _load_values(self) -> None:
        s = self._settings
        self._enabled_cb.setChecked(bool(s.get("paperhub_enabled")))
        self._api_key_edit.setText(str(s.get("paperhub_api_key") or ""))

        target_model = str(s.get("paperhub_model") or PAPERHUB_MODELS[0][1])
        for btn in self._model_group.buttons():
            if btn.property("model_id") == target_model:
                btn.setChecked(True)
                break
        else:
            first_btn = self._model_group.button(0)
            if first_btn:
                first_btn.setChecked(True)

        target_strategy = str(s.get("paperhub_strategy") or "unmatched_only")
        for btn in self._strategy_group.buttons():
            if btn.property("strategy_value") == target_strategy:
                btn.setChecked(True)
                break
        else:
            first_btn = self._strategy_group.button(0)
            if first_btn:
                first_btn.setChecked(True)

        self._reasoning_cb.setChecked(bool(s.get("paperhub_reasoning_enabled", True)))
        self._temperature_spin.setValue(float(s.get("paperhub_temperature", 0.7)))
        self._max_tokens_spin.setValue(int(s.get("paperhub_max_tokens", 2048)))

    def _collect_values(self) -> Dict[str, Any]:
        selected_model = PAPERHUB_MODELS[0][1]
        for btn in self._model_group.buttons():
            if btn.isChecked():
                selected_model = btn.property("model_id")
                break

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
        QApplication.processEvents()

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
# 辅助组件
# ---------------------------------------------------------------------------

def _separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setFrameShadow(QFrame.Sunken)
    return sep
