from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from app.ai_settings_store import DEFAULT_AI_SETTINGS, load_ai_settings, save_ai_settings


class AiSettingsDialog(QDialog):
    """可选模块：Claude / Gemini API 配置（密钥保存在本地 data/ai_settings.json）。"""

    def __init__(self, data_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self._data_dir = data_dir
        self.setWindowTitle("AI 辅助翻译设置")
        self.resize(520, 420)

        self._settings: Dict[str, Any] = load_ai_settings(data_dir)

        root = QVBoxLayout(self)

        tip = QLabel(
            "API Key 仅保存在本机 data/ai_settings.json，请勿分享或提交到版本库。\n"
            "翻译时：先用词表最长匹配，再对「词表外」片段调用所选模型补全整句。"
        )
        tip.setWordWrap(True)
        root.addWidget(tip)

        grp = QGroupBox("总开关")
        form = QFormLayout(grp)
        self._enabled = QCheckBox("启用 AI 辅助翻译（处理词库外词汇）")
        self._enabled.setChecked(bool(self._settings.get("enabled")))
        form.addRow(self._enabled)

        self._oov_only = QCheckBox("仅在存在词表外片段时调用 API（推荐）")
        self._oov_only.setChecked(bool(self._settings.get("ai_for_oov_only", True)))
        form.addRow(self._oov_only)

        root.addWidget(grp)

        grp2 = QGroupBox("提供商")
        form2 = QFormLayout(grp2)
        self._provider = QComboBox()
        self._provider.addItem("Anthropic Claude", "claude")
        self._provider.addItem("Google Gemini", "gemini")
        idx = 0 if str(self._settings.get("provider")) == "claude" else 1
        self._provider.setCurrentIndex(idx)
        form2.addRow("使用", self._provider)

        self._claude_key = QLineEdit()
        self._claude_key.setEchoMode(QLineEdit.Password)
        self._claude_key.setText(str(self._settings.get("claude_api_key") or ""))
        form2.addRow("Claude API Key", self._claude_key)

        self._claude_model = QLineEdit(str(self._settings.get("claude_model") or ""))
        form2.addRow("Claude 模型", self._claude_model)

        self._gemini_key = QLineEdit()
        self._gemini_key.setEchoMode(QLineEdit.Password)
        self._gemini_key.setText(str(self._settings.get("gemini_api_key") or ""))
        form2.addRow("Gemini API Key", self._gemini_key)

        self._gemini_model = QLineEdit(str(self._settings.get("gemini_model") or ""))
        form2.addRow("Gemini 模型", self._gemini_model)

        root.addWidget(grp2)

        btn = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn.button(QDialogButtonBox.Save).setText("保存")
        btn.accepted.connect(self._on_save)
        btn.rejected.connect(self.reject)
        root.addWidget(btn)

        self._apply_defaults_placeholder()

    def _apply_defaults_placeholder(self) -> None:
        if not self._claude_model.text().strip():
            self._claude_model.setText(str(DEFAULT_AI_SETTINGS["claude_model"]))
        if not self._gemini_model.text().strip():
            self._gemini_model.setText(str(DEFAULT_AI_SETTINGS["gemini_model"]))

    def _on_save(self) -> None:
        self._settings = {
            "enabled": self._enabled.isChecked(),
            "provider": self._provider.currentData(),
            "claude_api_key": self._claude_key.text().strip(),
            "claude_model": self._claude_model.text().strip() or DEFAULT_AI_SETTINGS["claude_model"],
            "gemini_api_key": self._gemini_key.text().strip(),
            "gemini_model": self._gemini_model.text().strip() or DEFAULT_AI_SETTINGS["gemini_model"],
            "ai_for_oov_only": self._oov_only.isChecked(),
        }
        try:
            save_ai_settings(self._data_dir, self._settings)
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self.accept()

    def settings(self) -> Dict[str, Any]:
        return dict(self._settings)
