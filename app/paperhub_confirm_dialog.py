"""
AI 建议翻译确认对话框（confirm 策略）。

显示 AI 生成的翻译候选与新词建议，让用户：
  - 采用建议：直接接受 AI 翻译结果
  - 修改后采用：在对话框中编辑后接受
  - 放弃：回退到规则翻译结果

确认后，如果有新创词汇，询问用户是否添加到词库。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.paperhub_client import NewWord, PaperHubResult
from app.ui_theme import theme_manager


class ConfirmResult:
    """用户确认后的结果。"""
    accepted: bool
    conlang: str
    tts: str
    new_words: List[NewWord]

    def __init__(
        self,
        accepted: bool,
        conlang: str = "",
        tts: str = "",
        new_words: Optional[List[NewWord]] = None,
    ) -> None:
        self.accepted = accepted
        self.conlang = conlang
        self.tts = tts
        self.new_words = new_words or []


class PaperHubConfirmDialog(QDialog):
    """AI 建议翻译确认对话框。"""

    def __init__(
        self,
        ai_result: PaperHubResult,
        rule_conlang: str,
        rule_tts: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ai_result = ai_result
        self._rule_conlang = rule_conlang
        self._rule_tts = rule_tts
        self._confirm_result: Optional[ConfirmResult] = None

        # 新词表格中的可编辑单元格
        self._new_word_edits: List[Dict[str, QLineEdit]] = []

        self.setWindowTitle("AI 建议翻译")
        self.setMinimumWidth(640)
        self.setMinimumHeight(420)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── 标题 ─────────────────────────────────────────────────────
        title = QLabel("AI 建议翻译")
        title.setProperty("class", "heading")
        layout.addWidget(title)

        # ── 自创语文本 ───────────────────────────────────────────────
        conlang_grp = QGroupBox("自创语文本")
        conlang_layout = QVBoxLayout(conlang_grp)
        self._conlang_edit = QPlainTextEdit()
        self._conlang_edit.setPlainText(self._ai_result.conlang)
        self._conlang_edit.setMinimumHeight(80)
        conlang_layout.addWidget(self._conlang_edit)
        layout.addWidget(conlang_grp)

        # ── TTS 音译 ──────────────────────────────────────────────────
        tts_grp = QGroupBox("TTS 音译")
        tts_layout = QVBoxLayout(tts_grp)
        self._tts_edit = QPlainTextEdit()
        self._tts_edit.setPlainText(self._ai_result.tts)
        self._tts_edit.setMinimumHeight(60)
        self._tts_edit.setMaximumHeight(100)
        tts_layout.addWidget(self._tts_edit)
        layout.addWidget(tts_grp)

        # ── AI 新词建议 ───────────────────────────────────────────────
        new_words = self._ai_result.new_words
        if new_words:
            nw_grp = QGroupBox("AI 为新词建议")
            nw_layout = QVBoxLayout(nw_grp)

            # 表格：中文 | 自创语 | TTS 拼写 | 构词逻辑
            table = QTableWidget(len(new_words), 4)
            table.setHorizontalHeaderLabels(["中文", "自创语", "TTS 拼写", "构词逻辑"])
            table.horizontalHeader().setStretchLastSection(True)
            table.setAlternatingRowColors(True)

            self._new_word_edits = []
            for row_idx, nw in enumerate(new_words):
                edits: Dict[str, QLineEdit] = {}
                for col_idx, (attr, placeholder) in enumerate([
                    ("chinese", "中文原词"),
                    ("conlang", "自创语"),
                    ("tts", "TTS友好拼写"),
                    ("logic", "构词逻辑说明"),
                ]):
                    edit = QLineEdit(str(getattr(nw, attr, "")))
                    edit.setPlaceholderText(placeholder)
                    table.setCellWidget(row_idx, col_idx, edit)
                    edits[attr] = edit

                self._new_word_edits.append(edits)

            table.resizeColumnsToContents()
            nw_layout.addWidget(table)
            layout.addWidget(nw_grp)

        # ── 错误提示（如果有） ────────────────────────────────────────
        if self._ai_result.error:
            error_lbl = QLabel(f"⚠ {self._ai_result.error}")
            error_lbl.setStyleSheet(
                f"color: {theme_manager.token('color_status_error')}; "
                f"font-size: {theme_manager.token('font_size_sm')};"
            )
            error_lbl.setWordWrap(True)
            layout.addWidget(error_lbl)

        layout.addStretch(1)

        # ── 按钮行 ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        btn_accept = QPushButton("采用建议")
        btn_accept.setMinimumWidth(100)
        btn_accept.setToolTip("直接接受 AI 的翻译建议")
        btn_accept.clicked.connect(self._on_accept)
        btn_row.addWidget(btn_accept)

        btn_edit_accept = QPushButton("修改后采用")
        btn_edit_accept.setMinimumWidth(100)
        btn_edit_accept.setToolTip("修改翻译内容后采用")
        btn_edit_accept.clicked.connect(self._on_edit_accept)
        btn_row.addWidget(btn_edit_accept)

        btn_discard = QPushButton("放弃")
        btn_discard.setMinimumWidth(80)
        btn_discard.setToolTip("放弃 AI 建议，使用规则翻译结果")
        btn_discard.clicked.connect(self._on_discard)
        btn_row.addWidget(btn_discard)

        layout.addLayout(btn_row)

    def _collect_new_words(self) -> List[NewWord]:
        """从表格中收集编辑后的新词数据。"""
        result: List[NewWord] = []
        for edits in self._new_word_edits:
            nw = NewWord(
                chinese=edits["chinese"].text().strip(),
                conlang=edits["conlang"].text().strip(),
                ipa="",  # IPA 不在编辑表格中
                tts=edits["tts"].text().strip(),
                logic=edits["logic"].text().strip(),
            )
            if nw.chinese and nw.conlang:
                result.append(nw)
        return result

    def _on_accept(self) -> None:
        """直接采用 AI 建议。"""
        self._confirm_result = ConfirmResult(
            accepted=True,
            conlang=self._ai_result.conlang,
            tts=self._ai_result.tts,
            new_words=self._ai_result.new_words,
        )
        self.accept()

    def _on_edit_accept(self) -> None:
        """修改后采用：取当前编辑框的内容。"""
        edited_conlang = self._conlang_edit.toPlainText().strip()
        edited_tts = self._tts_edit.toPlainText().strip()

        if not edited_conlang:
            QMessageBox.warning(self, "内容为空", "自创语文本不能为空，请填写或放弃。")
            return

        edited_new_words = self._collect_new_words()

        self._confirm_result = ConfirmResult(
            accepted=True,
            conlang=edited_conlang,
            tts=edited_tts,
            new_words=edited_new_words,
        )
        self.accept()

    def _on_discard(self) -> None:
        """放弃 AI 建议，使用规则翻译结果。"""
        self._confirm_result = ConfirmResult(
            accepted=False,
            conlang=self._rule_conlang,
            tts=self._rule_tts,
            new_words=[],  # 放弃时不上报新词
        )
        self.reject()

    def get_result(self) -> Optional[ConfirmResult]:
        """对话框关闭后获取用户确认结果。"""
        return self._confirm_result