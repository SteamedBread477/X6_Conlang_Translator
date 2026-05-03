"""
将未匹配词汇批量添加到主词库和 TTS 映射表的对话框。

用户填写：
  - 中文词（预填）→ 自创语翻译（写入 Conlang_Master_Library.json）
  - 自创语翻译 → TTS 拼写（写入 Mapping_Rules.csv；留空则与自创语相同）

点击「保存」后，若写入成功则返回 QDialog.Accepted，
调用方应随后调用 refresh_materials_from_disk 刷新内存词库索引。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


# 词性选项列表（缩写 + 全称）
POS_OPTIONS: List[str] = [
    "",               # 不标注
    ".v/动词",
    ".n/名词",
    ".a/形容词",
    ".d/副词",
    ".r/代词",
    ".p/介词",
    ".c/连词",
    ".m/数词",
    ".q/量词",
    ".u/助词",
    ".i/感叹词",
]


class AddWordDialog(QDialog):
    """将未匹配词汇批量添加到词库的对话框。"""

    def __init__(
        self,
        unmatched_words: List[str],
        master_library_path: Path,
        mapping_rules_path: Path,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.unmatched_words = unmatched_words
        self.master_library_path = master_library_path
        self.mapping_rules_path = mapping_rules_path

        # 每条: (中文词, conlang_edit, tts_edit, pos_combo)
        self._entries: List[Tuple[str, QLineEdit, QLineEdit, QComboBox]] = []

        self.setWindowTitle("将未匹配词汇添加到词库")
        self.setMinimumWidth(580)
        self.setMinimumHeight(320)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        hint = QLabel(
            "以下词汇在词库中没有对应翻译，请手动填写自创语翻译与 TTS 拼写后点击「保存」。\n"
            "TTS 拼写留空时将自动使用自创语翻译作为拼写；整行留空则跳过该词。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        container = QWidget()
        form = QFormLayout(container)
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("自创语翻译"), 1)
        header_row.addSpacing(8)
        header_row.addWidget(QLabel("TTS 拼写（留空同翻译）"), 1)
        header_row.addSpacing(8)
        header_row.addWidget(QLabel("词性"), 1)
        form.addRow("词汇：", _layout_to_widget(header_row))

        self._entries = []
        for word in self.unmatched_words:
            conlang_edit = QLineEdit()
            conlang_edit.setPlaceholderText("自创语翻译")
            tts_edit = QLineEdit()
            tts_edit.setPlaceholderText("TTS 拼写（留空同翻译）")

            pos_combo = QComboBox()
            pos_combo.addItems(POS_OPTIONS)
            pos_combo.setCurrentIndex(0)  # 默认不标注
            pos_combo.setFixedWidth(120)

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(conlang_edit, 1)
            row_layout.addSpacing(8)
            row_layout.addWidget(tts_edit, 1)
            row_layout.addSpacing(8)
            row_layout.addWidget(pos_combo)

            form.addRow(f"{word}：", row_widget)
            self._entries.append((word, conlang_edit, tts_edit, pos_combo))

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存到词库")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    def _on_save(self) -> None:
        # (中文+词性, 自创语, TTS) 三元组，只收集填了自创语的行
        to_add: List[Tuple[str, str, str]] = []
        for source_word, conlang_edit, tts_edit, pos_combo in self._entries:
            conlang = conlang_edit.text().strip()
            tts = tts_edit.text().strip() or conlang
            pos = pos_combo.currentText().strip()
            if conlang:
                # 拼接词性到中文词 key（如 "那个(.n/指示代词)"）
                zh_key = source_word + f"({pos})" if pos else source_word
                to_add.append((zh_key, conlang, tts))

        if not to_add:
            QMessageBox.information(self, "提示", "没有填写任何词汇，已取消。")
            self.reject()
            return

        errors: List[str] = []

        try:
            self._write_master_library([(src, con) for src, con, _ in to_add])
        except Exception as exc:
            errors.append(f"主词库写入失败：{exc}")

        try:
            self._write_mapping_rules([(con, tts) for _, con, tts in to_add])
        except Exception as exc:
            errors.append(f"映射表写入失败：{exc}")

        if errors:
            QMessageBox.critical(self, "写入失败", "\n".join(errors))
        else:
            QMessageBox.information(
                self,
                "保存成功",
                f"已添加 {len(to_add)} 条词汇到词库与映射表。\n"
                "界面将自动刷新词库索引。",
            )
            self.accept()

    # ------------------------------------------------------------------
    def _write_master_library(self, pairs: List[Tuple[str, str]]) -> None:
        """将 (中文, 自创语) 追加到 Conlang_Master_Library.json。"""
        path = self.master_library_path
        data: Any = {}
        if path.is_file():
            raw = path.read_text(encoding="utf-8").strip()
            if raw and raw not in ("{}", ""):
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {}

        if isinstance(data, dict):
            for zh, con in pairs:
                data[zh] = con
        elif isinstance(data, list):
            existing_zh = {
                item.get("zh") or item.get("中文") or item.get("source")
                for item in data
                if isinstance(item, dict)
            }
            for zh, con in pairs:
                if zh not in existing_zh:
                    data.append({"zh": zh, "conlang": con})
        else:
            data = {zh: con for zh, con in pairs}

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_mapping_rules(self, pairs: List[Tuple[str, str]]) -> None:
        """将 (自创语, TTS拼写) 追加到 Mapping_Rules.csv。"""
        path = self.mapping_rules_path
        rows: List[List[str]] = []
        existing_words: set[str] = set()

        if path.is_file():
            with path.open(newline="", encoding="utf-8-sig") as fh:
                reader = csv.reader(fh)
                rows = list(reader)
            for row in rows[1:]:
                if row:
                    existing_words.add(row[0].strip())

        if not rows:
            rows = [["自创语词汇", "IPA音标", "TTS友好拼写"]]

        for con, tts in pairs:
            if con and con not in existing_words:
                rows.append([con, "", tts])
                existing_words.add(con)

        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerows(rows)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def _layout_to_widget(layout: QHBoxLayout) -> QWidget:
    w = QWidget()
    w.setLayout(layout)
    return w
