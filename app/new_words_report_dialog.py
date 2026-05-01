"""
新创词汇报告对话框（阶段十）。

展示本次翻译中 PaperHub AI 创造的所有新词汇：
  - 表格：中文 | 自创语 | TTS拼写 | 构词逻辑
  - 按钮：导出词汇表 / 全部添加到词库 / 关闭

公开接口：
  NewWordsReportDialog(new_words, ai_model, parent)
"""
from __future__ import annotations

import csv
from typing import List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.paperhub_client import NewWord
from app.ui_theme import theme_manager


class NewWordsReportDialog(QDialog):
    """新创词汇报告对话框。"""

    def __init__(
        self,
        new_words: List[NewWord],
        ai_model: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._new_words = new_words
        self._ai_model = ai_model
        self._added_to_lexicon = False

        self.setWindowTitle("新创词汇报告")
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── 标题 ──────────────────────────────────────────────────
        header = QLabel(f"本次翻译共创造 {len(new_words)} 个新词汇：")
        header.setProperty("class", "title")
        layout.addWidget(header)

        # ── 表格 ──────────────────────────────────────────────────
        self._table = QTableWidget(len(new_words), 4)
        self._table.setHorizontalHeaderLabels(["中文", "自创语", "TTS拼写", "构词逻辑"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)

        for row_idx, nw in enumerate(new_words):
            self._table.setItem(row_idx, 0, QTableWidgetItem(nw.chinese))
            self._table.setItem(row_idx, 1, QTableWidgetItem(nw.conlang))
            self._table.setItem(row_idx, 2, QTableWidgetItem(nw.tts))
            self._table.setItem(row_idx, 3, QTableWidgetItem(nw.logic))

        layout.addWidget(self._table)

        # ── AI来源说明 ─────────────────────────────────────────────
        if ai_model:
            note = QLabel(f"※ 所有新创词汇均由 PaperHub AI（{ai_model}）生成")
            note.setStyleSheet(theme_manager.inline_style(
                color="color_text_muted",
                font_style="italic",
            ))
            layout.addWidget(note)

        # ── 按钮 ──────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_export = QPushButton("导出词汇表")
        btn_export.clicked.connect(self._export_vocab)
        btn_row.addWidget(btn_export)

        btn_add = QPushButton("全部添加到词库")
        btn_add.clicked.connect(self._add_to_lexicon)
        btn_row.addWidget(btn_add)

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def get_added_to_lexicon(self) -> bool:
        """返回是否已将词汇添加到词库。"""
        return self._added_to_lexicon

    def _export_vocab(self) -> None:
        """导出词汇表为 CSV 文件。"""
        from PyQt5.QtWidgets import QFileDialog
        from pathlib import Path

        default_name = "new_words_vocab.csv"
        output_path, _ = QFileDialog.getSaveFileName(
            self, "导出词汇表",
            str(Path.home() / default_name),
            "CSV Files (*.csv);;All Files (*)",
        )
        if not output_path:
            return

        try:
            with open(output_path, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["中文", "自创语", "TTS拼写", "构词逻辑", "AI模型"])
                for nw in self._new_words:
                    writer.writerow([
                        nw.chinese, nw.conlang, nw.tts, nw.logic, self._ai_model,
                    ])
            msg = "词汇表已导出到：" + "\n" + output_path
            QMessageBox.information(self, "导出成功", msg)
        except Exception as exc:
            msg = "导出 CSV 文件失败：" + "\n" + str(exc)
            QMessageBox.critical(self, "导出失败", msg)

    def _add_to_lexicon(self) -> None:
        """将所有新创词汇添加到当前语言的词库。"""
        # 通知调用方执行词库更新
        self._added_to_lexicon = True
        msg = "词汇将在关闭对话框后自动添加到词库。" + "\n" + "请确保已选中正确的语言。"
        QMessageBox.information(self, "已标记", msg)