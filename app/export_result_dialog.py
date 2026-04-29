"""
导出完成对话框（阶段十）。

翻译结果导出 Excel 后弹出，展示统计信息并提供操作按钮：
  - 查看新创词汇
  - 打开文件夹
  - 打开文件
  - 关闭

公开接口：
  ExportResultDialog(stats, output_path, new_words, parent)
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.paperhub_client import NewWord


class ExportResultDialog(QDialog):
    """导出完成对话框，展示统计与操作按钮。"""

    def __init__(
        self,
        stats: Dict[str, Any],
        output_path: str,
        new_words: List[NewWord],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._stats = stats
        self._output_path = output_path
        self._new_words = new_words

        self.setWindowTitle("导出完成")
        self.setMinimumWidth(420)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ── 标题 ──────────────────────────────────────────────────
        title = QLabel("✓ 文件已保存")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2e7d32;")
        layout.addWidget(title)

        # ── 路径 ──────────────────────────────────────────────────
        path_label = QLabel(f"路径：{output_path}")
        path_label.setWordWrap(True)
        path_label.setStyleSheet("color: #555;")
        layout.addWidget(path_label)

        # ── 统计 ──────────────────────────────────────────────────
        total = stats.get("total_rows", 0)
        success = stats.get("success_count", 0)
        failed = stats.get("failed_count", 0)
        ai_gen = stats.get("ai_generated_count", 0)
        new_w = stats.get("new_words_count", 0)
        model = stats.get("ai_model", "")

        stats_lines = [
            f"总行数：{total}",
            f"成功：{success}",
            f"失败：{failed}",
            f"AI生成：{ai_gen} 行",
            f"新增词汇：{new_w} 个",
        ]
        if model:
            stats_lines.append(f"PaperHub模型：{model}")
        stats_text = "\n".join(stats_lines)

        stats_label = QLabel(stats_text)
        stats_label.setStyleSheet("padding: 8px; background: #f5f5f5; border-radius: 4px;")
        layout.addWidget(stats_label)

        # ── 按钮 ──────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_new_words = QPushButton("查看新创词汇")
        btn_new_words.setEnabled(len(new_words) > 0)
        btn_new_words.clicked.connect(self._show_new_words)
        btn_row.addWidget(btn_new_words)

        btn_open_folder = QPushButton("打开文件夹")
        btn_open_folder.clicked.connect(self._open_folder)
        btn_row.addWidget(btn_open_folder)

        btn_open_file = QPushButton("打开文件")
        btn_open_file.clicked.connect(self._open_file)
        btn_row.addWidget(btn_open_file)

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    def _show_new_words(self) -> None:
        """弹出新创词汇报告对话框。"""
        from app.new_words_report_dialog import NewWordsReportDialog
        model = self._stats.get("ai_model", "")
        dlg = NewWordsReportDialog(self._new_words, model, parent=self)
        dlg.exec_()

    def _open_folder(self) -> None:
        """打开输出文件所在文件夹。"""
        folder = os.path.dirname(self._output_path)
        if folder:
            os.startfile(folder)

    def _open_file(self) -> None:
        """直接打开输出的 Excel 文件。"""
        if os.path.isfile(self._output_path):
            os.startfile(self._output_path)
        else:
            QMessageBox.warning(self, "文件不存在", "导出文件未找到。")