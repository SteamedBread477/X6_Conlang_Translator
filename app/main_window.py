from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.add_word_dialog import AddWordDialog
from app.asset_validation import check_asset
from app.unmatched_words_dialog import UnmatchedWordEntry, UnmatchedWordsDialog
from app.history_writer import append_translation_record
from app.material_service import (
    import_material_files,
    load_snapshot_if_any,
    refresh_materials_from_disk,
)
from app.paperhub_client import (
    NewWord,
    PaperHubResult,
    translate_with_paperhub,
)
from app.paperhub_confirm_dialog import PaperHubConfirmDialog
from app.paperhub_settings import load_paperhub_settings
from app.paperhub_settings_dialog import PaperHubSettingsDialog
from app.rule_translator import RuleTranslationResult, translate_multiline_rule
from app.storage import JsonStorage
from app.ui_theme import UITheme

FILE_KEYS = ("whitepaper", "master_library", "mapping_rules", "translation_history")


# ---------------------------------------------------------------------------
# PaperHub 异步翻译线程
# ---------------------------------------------------------------------------

class _PaperHubTranslateThread(QThread):
    """后台线程执行 PaperHub AI 翻译，避免阻塞 UI。"""

    finished = pyqtSignal(object)  # PaperHubResult

    def __init__(
        self,
        settings: Dict[str, Any],
        bundle: Dict[str, Any],
        text: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._bundle = bundle
        self._text = text

    def run(self) -> None:
        try:
            result = translate_with_paperhub(self._settings, self._bundle, self._text)
        except Exception as exc:
            result = PaperHubResult(error=str(exc))
        self.finished.emit(result)


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Nikki Conlang Forge 主窗口（资料管理 + PaperHub AI 翻译核心）。"""

    def __init__(self) -> None:
        super().__init__()
        self.storage = JsonStorage(Path(__file__).resolve().parent.parent / "data")
        self.state = self.storage.load_state()

        self._splitter: Optional[QSplitter] = None
        self.language_list: Optional[QListWidget] = None
        self._status_labels: Dict[str, QLabel] = {}
        self._batch_body: Optional[QWidget] = None
        self._batch_toggle_btn: Optional[QPushButton] = None
        self._batch_expanded = False

        self.source_input: Optional[QPlainTextEdit] = None
        self.target_output: Optional[QPlainTextEdit] = None
        self.tts_output: Optional[QPlainTextEdit] = None
        self.batch_log: Optional[QPlainTextEdit] = None
        self.batch_progress: Optional[QProgressBar] = None
        self.batch_path_display: Optional[QLabel] = None
        self._excel_path: str = ""

        # AI 翻译进度条（在单句翻译区下方）
        self._ai_progress: Optional[QProgressBar] = None
        self._ai_progress_label: Optional[QLabel] = None

        self._material_by_lang: Dict[str, Dict] = {}
        self._paperhub_settings: Dict = load_paperhub_settings(self.storage.base_dir)

        # 翻译统计与未匹配词管理
        self._stats_label: Optional[QLabel] = None
        self._add_word_btn: Optional[QPushButton] = None
        self._last_unmatched: List[str] = []
        self._last_rule_result: Optional[RuleTranslationResult] = None

        # PaperHub AI 翻译线程与状态
        self._ph_thread: Optional[_PaperHubTranslateThread] = None
        self._ph_rule_result: Optional[RuleTranslationResult] = None
        self._ph_text: str = ""
        self._ph_lang: Optional[Dict] = None
        self._ph_bundle: Dict = {}
        self._ph_lexicon: Dict[str, str] = {}
        self._ph_tts_map: Dict[str, str] = {}

        self._build_menu()
        self._build_central()
        self._load_languages()
        self.statusBar().showMessage("就绪")

    # ── 菜单 ──────────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        menubar = QMenuBar(self)
        self.setMenuBar(menubar)

        file_menu = menubar.addMenu("文件")
        act_import = QAction("导入资料…", self)
        act_import.triggered.connect(self.open_import_dialog)
        file_menu.addAction(act_import)
        file_menu.addSeparator()
        act_quit = QAction("退出", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(QApplication.instance().quit)
        file_menu.addAction(act_quit)

        edit_menu = menubar.addMenu("编辑")
        act_add = QAction("新增语言", self)
        act_add.triggered.connect(self.add_language)
        act_rename = QAction("重命名当前语言", self)
        act_rename.triggered.connect(self.rename_current_language)
        act_notes = QAction("语言备注…", self)
        act_notes.triggered.connect(self.edit_language_notes)
        edit_menu.addAction(act_add)
        edit_menu.addAction(act_rename)
        edit_menu.addSeparator()
        edit_menu.addAction(act_notes)

        tools_menu = menubar.addMenu("设置")
        act_ai = QAction("PaperHub 设置…", self)
        act_ai.triggered.connect(self._open_paperhub_settings)
        tools_menu.addAction(act_ai)

        help_menu = menubar.addMenu("帮助")
        act_about = QAction("关于", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    # ── 中央区域 ──────────────────────────────────────────────────────

    def _build_central(self) -> None:
        self.setWindowTitle("Nikki Conlang Forge")
        self.resize(1280, 820)

        self._splitter = QSplitter(Qt.Horizontal)

        left = self._build_left_panel()
        left.setMinimumWidth(160)
        left.resize(200, left.height())

        right = self._build_right_panel()

        self._splitter.addWidget(left)
        self._splitter.addWidget(right)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([220, 1060])

        self.setCentralWidget(self._splitter)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("语言")
        title.setStyleSheet("font-weight: bold;")

        self.language_list = QListWidget()
        self.language_list.setSelectionMode(QListWidget.SingleSelection)
        self.language_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.language_list.customContextMenuRequested.connect(self._on_language_list_context_menu)
        self.language_list.currentRowChanged.connect(self._on_language_row_changed)
        self.language_list.itemDoubleClicked.connect(lambda _item: self.rename_current_language())

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ 新增")
        btn_add.setToolTip("添加新的自创语言页签")
        btn_add.clicked.connect(self.add_language)
        btn_row.addWidget(btn_add)
        btn_row.addStretch(1)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)

        assets_title = QLabel("当前语言资料")
        assets_title.setStyleSheet("font-weight: bold;")

        assets_box = QGroupBox()
        assets_form = QFormLayout(assets_box)
        assets_form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        self._status_labels = {
            "whitepaper": QLabel("—\u2003白皮书"),
            "master_library": QLabel("—\u2003主词库"),
            "mapping_rules": QLabel("—\u2003映射表"),
            "translation_history": QLabel("—\u2003翻译历史"),
        }
        for key in FILE_KEYS:
            lbl = self._status_labels[key]
            lbl.setTextFormat(Qt.RichText)
            assets_form.addRow(lbl)

        btn_import = QPushButton("导入资料")
        btn_import.clicked.connect(self.open_import_dialog)

        layout.addWidget(title)
        layout.addWidget(self.language_list, 1)
        layout.addLayout(btn_row)
        layout.addWidget(sep)
        layout.addWidget(assets_title)
        layout.addWidget(assets_box)
        layout.addWidget(btn_import)

        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(10)

        # ── 单句翻译区 ──────────────────────────────────────────────
        single = QGroupBox("单句翻译")
        single_layout = QVBoxLayout(single)
        single_layout.setSpacing(6)

        # 输入 / 输出 并排区域
        io_grid = QGridLayout()
        io_grid.setColumnStretch(0, 1)
        io_grid.setColumnStretch(1, 1)
        io_grid.setSpacing(4)

        # 中文输入 — 标题行
        src_hdr = QHBoxLayout()
        src_hdr.addWidget(QLabel("中文输入"))
        src_hdr.addStretch(1)
        btn_copy_src = QPushButton("复制")
        btn_copy_src.setFixedWidth(54)
        btn_copy_src.setToolTip("复制中文输入文本")
        src_hdr.addWidget(btn_copy_src)
        io_grid.addLayout(src_hdr, 0, 0)

        # 自创语输出 — 标题行
        con_hdr = QHBoxLayout()
        con_hdr.addWidget(QLabel("自创语输出"))
        con_hdr.addStretch(1)
        btn_copy_con = QPushButton("复制")
        btn_copy_con.setFixedWidth(54)
        btn_copy_con.setToolTip("复制自创语翻译结果")
        con_hdr.addWidget(btn_copy_con)
        io_grid.addLayout(con_hdr, 0, 1)

        self.source_input = QPlainTextEdit()
        self.source_input.setPlaceholderText("输入中文（可多行）…")
        self.target_output = QPlainTextEdit()
        self.target_output.setReadOnly(True)
        self.target_output.setPlaceholderText("自创语输出（【词】表示未在词库中匹配）")
        io_grid.addWidget(self.source_input, 1, 0)
        io_grid.addWidget(self.target_output, 1, 1)

        single_layout.addLayout(io_grid)

        # 翻译按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._translate_btn = QPushButton("翻译")
        self._translate_btn.setMinimumWidth(88)
        self._translate_btn.setToolTip("规则翻译（AI 辅助可在「设置→PaperHub 设置」中开启）")
        self._translate_btn.clicked.connect(self._on_translate_clicked)
        btn_row.addWidget(self._translate_btn)
        single_layout.addLayout(btn_row)

        # AI 翻译进度行（阶段六新增）
        ai_progress_row = QHBoxLayout()
        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 0)  # 无限循环模式（翻译进行中）
        self._ai_progress.setValue(0)
        self._ai_progress.setFormat("AI 翻译中…")
        self._ai_progress.setVisible(False)
        self._ai_progress.setMaximumHeight(18)
        ai_progress_row.addWidget(self._ai_progress, 1)
        self._ai_progress_label = QLabel("")
        self._ai_progress_label.setStyleSheet("color: #555; font-size: 11px;")
        ai_progress_row.addWidget(self._ai_progress_label)
        single_layout.addLayout(ai_progress_row)

        # TTS 音译区
        tts_hdr = QHBoxLayout()
        tts_hdr.addWidget(QLabel("TTS 音译"))
        tts_hdr.addStretch(1)
        btn_copy_tts = QPushButton("复制")
        btn_copy_tts.setFixedWidth(54)
        btn_copy_tts.setToolTip("复制 TTS 友好音译")
        tts_hdr.addWidget(btn_copy_tts)
        single_layout.addLayout(tts_hdr)

        self.tts_output = QPlainTextEdit()
        self.tts_output.setReadOnly(True)
        self.tts_output.setPlaceholderText("TTS 友好音译（供语音合成使用）")
        self.tts_output.setMaximumHeight(90)
        single_layout.addWidget(self.tts_output)

        # 统计行
        stats_row = QHBoxLayout()
        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet("color: #555; font-size: 12px;")
        stats_row.addWidget(self._stats_label, 1)

        self._add_word_btn = QPushButton("将未匹配词添加到词库…")
        self._add_word_btn.setVisible(False)
        self._add_word_btn.clicked.connect(self._on_add_unmatched_words)
        stats_row.addWidget(self._add_word_btn)
        single_layout.addLayout(stats_row)

        # 连接复制按钮
        btn_copy_src.clicked.connect(
            lambda: QApplication.clipboard().setText(
                self.source_input.toPlainText() if self.source_input else ""
            )
        )
        btn_copy_con.clicked.connect(
            lambda: QApplication.clipboard().setText(
                self.target_output.toPlainText() if self.target_output else ""
            )
        )
        btn_copy_tts.clicked.connect(
            lambda: QApplication.clipboard().setText(
                self.tts_output.toPlainText() if self.tts_output else ""
            )
        )

        outer.addWidget(single, 1)

        # ── 批量翻译区（可折叠） ────────────────────────────────────
        batch_wrap = QWidget()
        batch_outer = QVBoxLayout(batch_wrap)
        batch_outer.setContentsMargins(0, 0, 0, 0)
        batch_outer.setSpacing(4)

        self._batch_toggle_btn = QPushButton("批量翻译  ▶")
        self._batch_toggle_btn.setStyleSheet("text-align: left; padding: 6px;")
        self._batch_toggle_btn.clicked.connect(self._toggle_batch_section)

        self._batch_body = QWidget()
        batch_layout = QVBoxLayout(self._batch_body)
        batch_layout.setSpacing(8)

        batch_box = QGroupBox("批量翻译")
        inner = QVBoxLayout(batch_box)

        btn_row2 = QHBoxLayout()
        btn_pick = QPushButton("选择 Excel")
        btn_pick.clicked.connect(self._pick_excel)
        btn_start = QPushButton("开始翻译")
        btn_start.clicked.connect(self._on_batch_start)
        btn_export = QPushButton("导出文件")
        btn_export.clicked.connect(self._on_batch_export)
        btn_row2.addWidget(btn_pick)
        btn_row2.addWidget(btn_start)
        btn_row2.addWidget(btn_export)
        btn_row2.addStretch(1)

        self.batch_path_display = QLabel("未选择文件")
        self.batch_path_display.setWordWrap(True)
        self.batch_path_display.setStyleSheet("color: #666;")

        self.batch_progress = QProgressBar()
        self.batch_progress.setRange(0, 100)
        self.batch_progress.setValue(0)
        self.batch_progress.setFormat("%p%")

        self.batch_log = QPlainTextEdit()
        self.batch_log.setReadOnly(True)
        self.batch_log.setPlaceholderText("日志：批量翻译进度将显示在这里")
        self.batch_log.setMaximumHeight(120)

        inner.addLayout(btn_row2)
        inner.addWidget(self.batch_path_display)
        inner.addWidget(self.batch_progress)
        inner.addWidget(QLabel("日志"))
        inner.addWidget(self.batch_log)

        batch_layout.addWidget(batch_box)

        self._batch_body.setVisible(False)
        batch_outer.addWidget(self._batch_toggle_btn)
        batch_outer.addWidget(self._batch_body)

        outer.addWidget(batch_wrap, 0)

        return panel

    # ── 辅助方法 ──────────────────────────────────────────────────────

    def _toggle_batch_section(self) -> None:
        self._batch_expanded = not self._batch_expanded
        if self._batch_body is not None:
            self._batch_body.setVisible(self._batch_expanded)
        if self._batch_toggle_btn is not None:
            self._batch_toggle_btn.setText(
                "批量翻译  ▼" if self._batch_expanded else "批量翻译  ▶"
            )

    def _load_languages(self) -> None:
        languages = self.state.get("languages", [])
        if not languages:
            lang = self.storage.create_language_record("默认语言", languages)
            languages = [lang]
            self.state["languages"] = languages
            self.storage.init_language_package(lang)
            self.storage.save_state(self.state)

        assert self.language_list is not None
        self.language_list.clear()
        for lang in languages:
            item = QListWidgetItem(self._language_row_text(lang))
            item.setData(Qt.UserRole, lang["id"])
            self.language_list.addItem(item)
        self.language_list.setCurrentRow(0)
        self._refresh_asset_status()
        self._refresh_status_bar()

    def _status_symbol_for_result(self, status: str) -> str:
        if status == "ok":
            return "✓"
        if status == "missing":
            return "○"
        return "✗"

    def _language_row_text(self, lang: Dict) -> str:
        parts: List[str] = []
        for key in FILE_KEYS:
            path = self.storage.asset_path(lang, key)
            result = check_asset(key, path)
            parts.append(self._status_symbol_for_result(result.status))
        return f"{lang.get('name', '未命名')}  {''.join(parts)}"

    def _refresh_list_item_for_language(self, lang_id: str) -> None:
        assert self.language_list is not None
        for i in range(self.language_list.count()):
            item = self.language_list.item(i)
            if item and item.data(Qt.UserRole) == lang_id:
                lang = self._language_by_id(lang_id)
                if lang:
                    item.setText(self._language_row_text(lang))
                break

    def _ensure_material_bundle(self, lang: Dict) -> None:
        bid = lang.get("id", "")
        if not bid or bid in self._material_by_lang:
            return
        snap = load_snapshot_if_any(self.storage, lang)
        if snap:
            self._material_by_lang[bid] = snap
        else:
            rep = refresh_materials_from_disk(self.storage, lang)
            self._material_by_lang[bid] = rep.bundle

    def _open_paperhub_settings(self) -> None:
        dlg = PaperHubSettingsDialog(self.storage.base_dir, self)
        if dlg.exec_() == QDialog.Accepted:
            self._paperhub_settings = load_paperhub_settings(self.storage.base_dir)
            self.statusBar().showMessage("PaperHub 设置已保存", 4000)

    def _language_by_id(self, lang_id: str) -> Optional[Dict]:
        for lang in self.state.get("languages", []):
            if lang.get("id") == lang_id:
                return lang
        return None

    def _on_language_row_changed(self, row: int) -> None:
        if row < 0:
            return
        lang = self.get_current_language()
        if lang is not None:
            self._ensure_material_bundle(lang)
        self._refresh_asset_status()
        self._refresh_status_bar()

    def _refresh_asset_status(self) -> None:
        lang = self.get_current_language()
        if not lang:
            for key in FILE_KEYS:
                lbl = self._status_labels.get(key)
                if lbl is not None:
                    lbl.setText(
                        f'<span style="color:{UITheme.STATUS_MISSING_COLOR}; font-weight:600;">○</span>'
                        f"\u2003{self._asset_label_title(key)}"
                    )
                    lbl.setToolTip("")
            return

        labels_short = {
            "whitepaper": "白皮书",
            "master_library": "主词库",
            "mapping_rules": "映射表",
            "translation_history": "翻译历史",
        }
        for key in FILE_KEYS:
            path = self.storage.asset_path(lang, key)
            result = check_asset(key, path)
            if result.status == "ok":
                color = UITheme.STATUS_OK_COLOR
                mark = "✓"
                tip = str(self.storage.asset_path(lang, key))
            elif result.status == "missing":
                color = UITheme.STATUS_MISSING_COLOR
                mark = "○"
                tip = "尚未加载或文件不存在"
            else:
                color = UITheme.STATUS_ERROR_COLOR
                mark = "✗"
                tip = result.message or "加载失败"

            lbl = self._status_labels.get(key)
            if lbl is not None:
                lbl.setText(
                    f'<span style="color:{color}; font-weight:600;">{mark}</span>'
                    f"\u2003{labels_short[key]}"
                )
                lbl.setToolTip(tip)

    def _asset_label_title(self, key: str) -> str:
        titles = {
            "whitepaper": "白皮书",
            "master_library": "主词库",
            "mapping_rules": "映射表",
            "translation_history": "翻译历史",
        }
        return titles[key]

    def get_current_language(self) -> Optional[Dict]:
        assert self.language_list is not None
        row = self.language_list.currentRow()
        languages: List[Dict] = self.state.get("languages", [])
        if row < 0 or row >= len(languages):
            return None
        return languages[row]

    def get_current_language_id(self) -> Optional[str]:
        lang = self.get_current_language()
        return lang["id"] if lang else None

    def get_language_material_bundle(self, lang_id: Optional[str] = None) -> Dict:
        """供翻译阶段使用：返回已解析的词库索引、TTS 映射、锚点与白皮书结构。"""
        if lang_id is None:
            lang = self.get_current_language()
            lang_id = lang["id"] if lang else None
        if not lang_id:
            return {}
        return dict(self._material_by_lang.get(lang_id, {}))

    def _refresh_status_bar(self) -> None:
        lang = self.get_current_language()
        if lang is None:
            self.statusBar().showMessage("暂无语言")
        else:
            self.statusBar().showMessage(f"当前语言：{lang['name']}")

    def _save_state(self) -> None:
        self.storage.save_state(self.state)

    # ── 语言管理 ──────────────────────────────────────────────────────

    def add_language(self) -> None:
        languages = self.state.setdefault("languages", [])
        default_name = self.storage.ensure_unique_language_name("新语言", languages)

        name, confirmed = QInputDialog.getText(
            self, "新增语言", "请输入语言名称：", text=default_name,
        )
        if not confirmed:
            return

        name = name.strip() or default_name

        language = self.storage.create_language_record(name, languages)
        languages.append(language)
        self.storage.init_language_package(language)

        assert self.language_list is not None
        item = QListWidgetItem(self._language_row_text(language))
        item.setData(Qt.UserRole, language["id"])
        self.language_list.addItem(item)
        self.language_list.setCurrentRow(self.language_list.count() - 1)
        self._save_state()
        self._refresh_asset_status()
        self._refresh_status_bar()

    def rename_current_language(self) -> None:
        current = self.get_current_language()
        if current is None:
            return

        name, confirmed = QInputDialog.getText(
            self, "重命名语言", "请输入新的语言名称：", text=current["name"],
        )
        if not confirmed:
            return

        name = name.strip()
        if not name:
            QMessageBox.warning(self, "名称无效", "语言名称不能为空。")
            return

        try:
            self.storage.rename_language(current, name, self.state.get("languages", []))
        except OSError as exc:
            QMessageBox.critical(self, "重命名失败", str(exc))
            return

        assert self.language_list is not None
        row = self.language_list.currentRow()
        item = self.language_list.item(row)
        if item:
            item.setText(self._language_row_text(current))

        self._save_state()
        self._refresh_status_bar()

    def edit_language_notes(self) -> None:
        lang = self.get_current_language()
        if lang is None:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"语言备注 — {lang['name']}")
        v = QVBoxLayout(dlg)
        text = QTextEdit()
        text.setPlainText(lang.get("notes", ""))
        v.addWidget(text)
        btn_row = QHBoxLayout()
        ok = QPushButton("确定")
        cancel = QPushButton("取消")
        btn_row.addStretch(1)
        btn_row.addWidget(ok)
        btn_row.addWidget(cancel)
        v.addLayout(btn_row)

        def accept() -> None:
            lang["notes"] = text.toPlainText()
            self._save_state()
            dlg.accept()

        ok.clicked.connect(accept)
        cancel.clicked.connect(dlg.reject)
        dlg.exec_()

    def open_import_dialog(self) -> None:
        lang = self.get_current_language()
        if lang is None:
            QMessageBox.information(self, "导入", "请先选择或新增一个语言。")
            return

        paths, _ = QFileDialog.getOpenFileNames(
            self, "导入资料（可多选）", str(Path.home()),
            "资料 (*.md *.txt *.json *.csv);;Markdown (*.md);;JSON (*.json);;CSV (*.csv);;所有文件 (*.*)",
        )
        if not paths:
            return

        report = import_material_files(self.storage, lang, list(paths))
        self._material_by_lang[lang["id"]] = report.bundle
        QMessageBox.information(self, "导入结果", "\n".join(report.lines))

        self._save_state()
        self._refresh_list_item_for_language(lang["id"])
        self._refresh_asset_status()

    def update_language_file(self, language_id: str, file_key: str, file_path: str) -> None:
        """保留与后续模块对接的钩子（当前阶段主要由导入对话框写入）。"""
        lang = self._language_by_id(language_id)
        if lang is None:
            return
        self.storage.import_external_files(lang, {file_key: file_path})
        self._save_state()
        report = refresh_materials_from_disk(self.storage, lang)
        self._material_by_lang[lang["id"]] = report.bundle
        self._refresh_list_item_for_language(language_id)
        if self.get_current_language_id() == language_id:
            self._refresh_asset_status()

    def _on_language_list_context_menu(self, pos) -> None:
        assert self.language_list is not None
        item = self.language_list.itemAt(pos)
        if item is None:
            return
        self.language_list.setCurrentItem(item)
        lang = self._language_by_id(item.data(Qt.UserRole))
        if lang is None:
            return

        menu = QMenu(self)
        act_rename = menu.addAction("重命名")
        act_delete = menu.addAction("删除…")
        menu.addSeparator()
        act_export = menu.addAction("导出语言包…")
        act_import_pack = menu.addAction("导入语言包…")

        global_pos = self.language_list.viewport().mapToGlobal(pos)
        chosen = menu.exec_(global_pos)
        if chosen == act_rename:
            self.rename_current_language()
        elif chosen == act_delete:
            self._delete_language_confirmed(lang)
        elif chosen == act_export:
            self._export_language_pack(lang)
        elif chosen == act_import_pack:
            self._import_language_pack(lang)

    def _delete_language_confirmed(self, lang: Dict) -> None:
        languages: List[Dict] = self.state.get("languages", [])
        if len(languages) <= 1:
            QMessageBox.information(self, "删除", "至少保留一种语言。")
            return

        folder = self.storage.language_dir(lang)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除语言「{lang['name']}」？\n\n以下资料文件夹将永久删除：\n{folder}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        assert self.language_list is not None
        row = self.language_list.currentRow()
        try:
            self.storage.delete_language_files(lang)
        except OSError as exc:
            QMessageBox.critical(self, "删除失败", str(exc))
            return

        self.state["languages"] = [x for x in languages if x["id"] != lang["id"]]
        self._save_state()

        self.language_list.takeItem(row)
        new_row = min(row, self.language_list.count() - 1)
        self.language_list.setCurrentRow(max(0, new_row))
        self._refresh_all_list_rows()
        self._refresh_asset_status()
        self._refresh_status_bar()

    def _refresh_all_list_rows(self) -> None:
        assert self.language_list is not None
        for row in range(self.language_list.count()):
            item = self.language_list.item(row)
            if item is None:
                continue
            lang = self._language_by_id(item.data(Qt.UserRole))
            if lang:
                item.setText(self._language_row_text(lang))

    def _export_language_pack(self, lang: Dict) -> None:
        default = f"{lang['name']}_语言包.zip"
        zip_path_str, _ = QFileDialog.getSaveFileName(
            self, "导出语言包", str(Path.home() / default), "Zip 压缩包 (*.zip)",
        )
        if not zip_path_str:
            return
        zip_path = Path(zip_path_str)
        try:
            count, _msg = self.storage.export_language_pack_zip(lang, zip_path)
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        if count < len(FILE_KEYS):
            QMessageBox.warning(
                self, "导出完成（不完整）",
                f"已打包 {count} / {len(FILE_KEYS)} 个文件。缺失项将以 ○ 显示在列表中。",
            )
        else:
            QMessageBox.information(self, "导出完成", f"已打包全部 {count} 个文件。")

    def _import_language_pack(self, lang: Dict) -> None:
        zip_path_str, _ = QFileDialog.getOpenFileName(
            self, "导入语言包", str(Path.home()), "Zip 压缩包 (*.zip)",
        )
        if not zip_path_str:
            return
        try:
            count, _ = self.storage.import_language_pack_zip(lang, Path(zip_path_str))
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        report = refresh_materials_from_disk(self.storage, lang)
        self._material_by_lang[lang["id"]] = report.bundle
        self._refresh_list_item_for_language(lang["id"])
        self._refresh_asset_status()
        QMessageBox.information(
            self, "导入完成",
            "\n".join(
                [f"已从压缩包写入 {count} 个识别到的资料文件。", ""] + report.lines
            ),
        )

    # ── 翻译核心（阶段六：完整 PaperHub AI 翻译流程）──────────────────

    def _on_translate_clicked(self) -> None:
        lang = self.get_current_language()
        if lang is None:
            return
        if self.source_input is None:
            return
        text = self.source_input.toPlainText()
        if not text.strip():
            self.statusBar().showMessage("请先输入中文", 4000)
            return

        # 防止重复点击（AI 线程运行中）
        if self._ph_thread is not None and self._ph_thread.isRunning():
            self.statusBar().showMessage("AI 翻译进行中，请等待完成", 4000)
            return

        self._ensure_material_bundle(lang)
        bundle = self._material_by_lang.get(lang["id"], {})

        # 规范化词库和 TTS 映射（过滤空键）
        raw_lexicon = bundle.get("lexicon") or {}
        lexicon: Dict[str, str] = {
            str(k): str(v) for k, v in raw_lexicon.items()
            if isinstance(k, str) and k.strip()
        }
        raw_tts = bundle.get("tts_map") or {}
        tts_map: Dict[str, str] = {
            str(k): str(v) for k, v in raw_tts.items()
            if isinstance(k, str) and k.strip()
        }

        # ── 始终执行规则翻译（提供匹配统计）────────────────────────
        rule_result = translate_multiline_rule(text, lexicon, tts_map)
        self._last_rule_result = rule_result

        # ── 判断是否需要 PaperHub AI ────────────────────────────────
        self._paperhub_settings = load_paperhub_settings(self.storage.base_dir)
        ph_enabled = bool(self._paperhub_settings.get("paperhub_enabled"))
        strategy = str(self._paperhub_settings.get("paperhub_strategy") or "unmatched_only")

        need_ai = ph_enabled and (
            strategy == "always"
            or strategy == "confirm"
            or (strategy == "unmatched_only" and bool(rule_result.unmatched_words))
        )

        if not need_ai:
            # 纯规则翻译 —— 直接显示结果
            self._display_translation_result(
                conlang=rule_result.conlang,
                tts=rule_result.phonetic,
                rule_result=rule_result,
                translation_mode="rule",
                ai_error="",
            )
            return

        # ── 需要 AI 翻译 —— 启动后台线程 ────────────────────────────
        # 先保存翻译上下文供线程回调使用
        self._ph_rule_result = rule_result
        self._ph_text = text
        self._ph_lang = lang
        self._ph_bundle = bundle
        self._ph_lexicon = lexicon
        self._ph_tts_map = tts_map

        # 显示进度动画
        if self._ai_progress is not None:
            self._ai_progress.setVisible(True)
            self._ai_progress.setFormat("AI 翻译中…")
        if self._ai_progress_label is not None:
            self._ai_progress_label.setText(f"正在调用 PaperHub AI（策略：{strategy}）…")
        self._translate_btn.setEnabled(False)
        self._translate_btn.setText("翻译中…")
        self.statusBar().showMessage("AI 翻译进行中，请稍候…")

        # 启动后台线程
        self._ph_thread = _PaperHubTranslateThread(
            self._paperhub_settings, bundle, text, self,
        )
        self._ph_thread.finished.connect(self._on_paperhub_thread_finished)
        self._ph_thread.start()

    def _on_paperhub_thread_finished(self, result_obj: Any) -> None:
        """PaperHub AI 翻译线程完成回调。"""
        # 恢复 UI 状态
        if self._ai_progress is not None:
            self._ai_progress.setVisible(False)
        if self._ai_progress_label is not None:
            self._ai_progress_label.setText("")
        self._translate_btn.setEnabled(True)
        self._translate_btn.setText("翻译")

        # 类型转换
        ph_result: PaperHubResult = result_obj if isinstance(result_obj, PaperHubResult) else PaperHubResult(error=str(result_obj))

        rule_result = self._ph_rule_result
        if rule_result is None:
            self.statusBar().showMessage("翻译异常：丢失规则翻译结果", 5000)
            return

        strategy = ph_result.strategy_used or str(self._paperhub_settings.get("paperhub_strategy") or "unmatched_only")
        lang = self._ph_lang
        if lang is None:
            self.statusBar().showMessage("翻译异常：丢失语言上下文", 5000)
            return

        # ── confirm 策略：弹出确认对话框 ────────────────────────────
        if strategy == "confirm" and not ph_result.error:
            confirm_dlg = PaperHubConfirmDialog(
                ai_result=ph_result,
                rule_conlang=rule_result.conlang,
                rule_tts=rule_result.phonetic,
                parent=self,
            )
            confirm_dlg.exec_()
            confirm_result = confirm_dlg.get_result()

            if confirm_result is not None and confirm_result.accepted:
                # 用户采用了 AI 建议（或修改后采用）
                conlang_out = confirm_result.conlang
                tts_out = confirm_result.tts
                translation_mode = "ai_confirm"

                # 询问是否将新词添加到词库
                if confirm_result.new_words:
                    self._ask_add_new_words_to_lexicon(confirm_result.new_words, lang)
            else:
                # 用户放弃了 AI 建议，使用规则翻译结果
                conlang_out = rule_result.conlang
                tts_out = rule_result.phonetic
                translation_mode = "rule_confirm_discarded"

            self._display_translation_result(
                conlang=conlang_out,
                tts=tts_out,
                rule_result=rule_result,
                translation_mode=translation_mode,
                ai_error="",
            )
            return

        # ── unmatched_only / always 策略 ─────────────────────────────
        conlang_out = rule_result.conlang
        tts_out = rule_result.phonetic
        translation_mode = "rule"
        ai_error = ""

        if ph_result.error:
            ai_error = ph_result.error
            # AI 失败时使用规则翻译回退结果
            # ph_result 可能已经包含回退的规则结果
            if ph_result.conlang:
                conlang_out = ph_result.conlang
                tts_out = ph_result.tts
                translation_mode = "ai_fallback"
        else:
            if ph_result.conlang:
                conlang_out = ph_result.conlang
                tts_out = ph_result.tts
                translation_mode = "ai_assisted"

            # 询问是否将新词添加到词库
            if ph_result.new_words:
                self._ask_add_new_words_to_lexicon(ph_result.new_words, lang)

        self._display_translation_result(
            conlang=conlang_out,
            tts=tts_out,
            rule_result=rule_result,
            translation_mode=translation_mode,
            ai_error=ai_error,
        )

    def _display_translation_result(
        self,
        conlang: str,
        tts: str,
        rule_result: RuleTranslationResult,
        translation_mode: str,
        ai_error: str,
    ) -> None:
        """统一更新输出框、统计栏、翻译历史与状态栏。"""
        lang = self.get_current_language()
        if lang is None:
            return

        # ── 更新输出框 ────────────────────────────────────────────
        if self.target_output is not None:
            self.target_output.setPlainText(conlang)
        if self.tts_output is not None:
            self.tts_output.setPlainText(tts)

        # ── 更新统计栏 ────────────────────────────────────────────
        rate_pct = int(rule_result.match_rate * 100)
        elapsed = rule_result.elapsed_ms
        unmatched = rule_result.unmatched_words
        emotion = rule_result.emotion

        stat_parts: List[str] = [
            f"匹配率 {rate_pct}%",
            f"耗时 {elapsed:.0f} ms",
        ]
        if unmatched:
            stat_parts.append(f"{len(unmatched)} 个词汇未找到")
        if translation_mode.startswith("ai"):
            stat_parts.append("AI 辅助")
        if emotion.label != "neutral":
            stat_parts.append(f"情绪: {emotion.display_name}")

        stats_text = "  ·  ".join(stat_parts)
        if self._stats_label is not None:
            self._stats_label.setText(stats_text)

        # ── 控制「添加到词库」按钮 ───────────────────────────────
        self._last_unmatched = unmatched
        if self._add_word_btn is not None:
            self._add_word_btn.setVisible(bool(unmatched))

        # ── 阶段七：自动弹出未匹配词汇处理对话框 ──────────────────
        # 仅在纯规则翻译有未匹配词时弹出（AI 辅助翻译的新词已通过
        # _ask_add_new_words_to_lexicon 处理，不需要重复弹出）
        if unmatched and translation_mode in ("rule", "rule_confirm_discarded", "ai_fallback"):
            self._auto_show_unmatched_words_dialog(lang, unmatched)

        # ── 写入翻译历史 ──────────────────────────────────────────
        text = self._ph_text or self.source_input.toPlainText() if self.source_input else ""
        try:
            hist_path = self.storage.asset_path(lang, "translation_history")
            append_translation_record(
                hist_path,
                source=text,
                conlang=conlang,
                phonetic=tts,
                unmatched_words=unmatched,
                target_language=lang["name"],
                translation_mode=translation_mode,
                emotion_label=emotion.label,
                emotion_intensity=emotion.intensity,
                tts_pitch_hint=emotion.tts_pitch_hint,
                tts_rate_hint=emotion.tts_rate_hint,
            )
        except Exception:
            pass  # 历史写入失败不阻断翻译主流程

        # ── 状态栏 & AI 错误提示 ───────────────────────────────────
        if ai_error:
            err_keywords = ("失败", "未填写", "缺少依赖", "API Key", "无效", "超时", "网络", "不存在")
            if any(k in ai_error for k in err_keywords):
                QMessageBox.warning(self, "PaperHub 翻译提示", ai_error)
            self.statusBar().showMessage(f"翻译完成 · {stats_text}", 10000)
        else:
            self.statusBar().showMessage(f"翻译完成 · {stats_text}", 8000)

    # ── 自动弹出未匹配词汇对话框（阶段七新增）─────────────────────

    def _auto_show_unmatched_words_dialog(
        self,
        lang: Dict,
        unmatched: List[str],
    ) -> None:
        """翻译完成后如果有未匹配词汇，自动弹出 UnmatchedWordsDialog。"""
        if not unmatched:
            return

        self._ensure_material_bundle(lang)
        bundle = self._material_by_lang.get(lang["id"], {})
        self._paperhub_settings = load_paperhub_settings(self.storage.base_dir)

        dlg = UnmatchedWordsDialog(
            unmatched_words=unmatched,
            bundle=bundle,
            paperhub_settings=self._paperhub_settings,
            parent=self,
        )
        if dlg.exec_() == QDialog.Accepted:
            entries = dlg.get_entries()
            filled = [e for e in entries if e.conlang]
            if filled:
                self._write_unmatched_entries_to_lexicon(filled, lang)
                self._last_unmatched = []
                if self._add_word_btn is not None:
                    self._add_word_btn.setVisible(False)
            else:
                self.statusBar().showMessage("没有需要保存的词汇", 3000)

    # ── 新词入库询问（阶段六新增）───────────────────────────────────

    def _ask_add_new_words_to_lexicon(self, new_words: List[NewWord], lang: Dict) -> None:
        """翻译完成后，如果有新创词汇，询问用户是否添加到词库。"""
        if not new_words:
            return

        # 构造展示文本
        word_lines: List[str] = []
        for nw in new_words:
            line = f"  {nw.chinese} → {nw.conlang}"
            if nw.tts:
                line += f"  (TTS: {nw.tts})"
            if nw.logic:
                line += f"  [构词: {nw.logic}]"
            word_lines.append(line)

        detail = "\n".join(word_lines)
        reply = QMessageBox.question(
            self,
            "添加新词到词库？",
            f"AI 翻译中创造了 {len(new_words)} 个新词汇：\n\n{detail}\n\n"
            "是否将这些新词添加到主词库和映射表？\n"
            "（添加后下次翻译时词库将包含这些词汇）",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        # 执行写入
        self._write_new_words_to_lexicon(new_words, lang)

    def _write_new_words_to_lexicon(self, new_words: List[NewWord], lang: Dict) -> None:
        """将 AI 创造的新词写入主词库和映射表。"""
        errors: List[str] = []

        # ── 写入主词库 JSON ────────────────────────────────────────
        master_path = self.storage.asset_path(lang, "master_library")
        try:
            data: Any = {}
            if master_path.is_file():
                raw = master_path.read_text(encoding="utf-8").strip()
                if raw and raw not in ("{}", ""):
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        data = {}

            if isinstance(data, dict):
                for nw in new_words:
                    data[nw.chinese] = nw.conlang
            elif isinstance(data, list):
                for nw in new_words:
                    data.append({"zh": nw.chinese, "conlang": nw.conlang})

            master_path.parent.mkdir(parents=True, exist_ok=True)
            master_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            errors.append(f"主词库写入失败：{exc}")

        # ── 写入映射表 CSV ────────────────────────────────────────
        mapping_path = self.storage.asset_path(lang, "mapping_rules")
        try:
            rows: List[List[str]] = []
            existing_words: set[str] = set()

            if mapping_path.is_file():
                with mapping_path.open(newline="", encoding="utf-8-sig") as fh:
                    reader = csv.reader(fh)
                    rows = list(reader)
                for row in rows[1:]:
                    if row:
                        existing_words.add(row[0].strip())

            if not rows:
                rows = [["自创语词汇", "IPA音标", "TTS友好拼写"]]

            for nw in new_words:
                if nw.conlang and nw.conlang not in existing_words:
                    ipa = nw.ipa or ""
                    tts = nw.tts or nw.conlang
                    rows.append([nw.conlang, ipa, tts])
                    existing_words.add(nw.conlang)

            with mapping_path.open("w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh)
                writer.writerows(rows)
        except Exception as exc:
            errors.append(f"映射表写入失败：{exc}")

        if errors:
            QMessageBox.critical(self, "写入失败", "\n".join(errors))
        else:
            # 刷新内存词库
            report = refresh_materials_from_disk(self.storage, lang)
            self._material_by_lang[lang["id"]] = report.bundle
            self._refresh_list_item_for_language(lang["id"])
            self._refresh_asset_status()
            self.statusBar().showMessage(
                f"已添加 {len(new_words)} 个新词到词库，重新翻译可生效", 5000
            )

    # ── 富元数据写入（阶段七新增）─────────────────────────────────────

    def _write_unmatched_entries_to_lexicon(
        self,
        entries: List[UnmatchedWordEntry],
        lang: Dict,
    ) -> None:
        """将 UnmatchedWordEntry（含富元数据）写入主词库和映射表。

        主词库写入格式（阶段七升级）：
          {
            "vocabulary": {
              "星之海": {
                "conlang": "aether'maris",
                "ipa": "ae-ther-ma-ris",
                "tts": "aethermaris",
                "logic": "星+aether组合",
                "created_by": "paperhub_ai",
                "created_time": "2025-04-29T10:30:00",
                "model": "qwen3-max"
              }
            }
          }
        """
        errors: List[str] = []

        # ── 写入主词库 JSON ────────────────────────────────────────
        master_path = self.storage.asset_path(lang, "master_library")
        try:
            data: Any = {}
            if master_path.is_file():
                raw = master_path.read_text(encoding="utf-8").strip()
                if raw and raw not in ("{}", ""):
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        data = {}

            # 确保顶层有 vocabulary 键
            if isinstance(data, dict):
                vocab = data.setdefault("vocabulary", {})
                if not isinstance(vocab, dict):
                    vocab = {}
                    data["vocabulary"] = vocab

                for entry in entries:
                    if not entry.conlang:
                        continue
                    # 检查是否已有该词条 — 如果有则更新，否则新增
                    existing = vocab.get(entry.chinese)
                    if isinstance(existing, dict):
                        # 已有富元数据条目 → 更新字段
                        existing["conlang"] = entry.conlang
                        existing["ipa"] = entry.ipa or existing.get("ipa", "")
                        existing["tts"] = entry.tts or existing.get("tts", "")
                        existing["logic"] = entry.logic or existing.get("logic", "")
                        if entry.created_by:
                            existing["created_by"] = entry.created_by
                        if entry.created_time:
                            existing["created_time"] = entry.created_time
                        if entry.model:
                            existing["model"] = entry.model
                    elif isinstance(existing, str):
                        # 旧格式（简单映射 "中文": "自创语"）→ 升级为富元数据
                        vocab[entry.chinese] = {
                            "conlang": entry.conlang,
                            "ipa": entry.ipa or "",
                            "tts": entry.tts or entry.conlang,
                            "logic": entry.logic or "",
                            "created_by": entry.created_by or "manual",
                            "created_time": entry.created_time or "",
                            "model": entry.model or "",
                        }
                    else:
                        # 新增条目
                        vocab[entry.chinese] = {
                            "conlang": entry.conlang,
                            "ipa": entry.ipa or "",
                            "tts": entry.tts or entry.conlang,
                            "logic": entry.logic or "",
                            "created_by": entry.created_by or "manual",
                            "created_time": entry.created_time or "",
                            "model": entry.model or "",
                        }

                # 同时保持顶层简单映射兼容性（规则翻译使用顶层键值对）
                for entry in entries:
                    if entry.conlang:
                        data[entry.chinese] = entry.conlang

            elif isinstance(data, list):
                # 列表格式 → 逐条追加
                for entry in entries:
                    if entry.conlang:
                        data.append({
                            "zh": entry.chinese,
                            "conlang": entry.conlang,
                            "ipa": entry.ipa,
                            "tts": entry.tts or entry.conlang,
                            "logic": entry.logic,
                            "created_by": entry.created_by or "manual",
                            "created_time": entry.created_time or "",
                            "model": entry.model or "",
                        })

            master_path.parent.mkdir(parents=True, exist_ok=True)
            master_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as exc:
            errors.append(f"主词库写入失败：{exc}")

        # ── 写入映射表 CSV ────────────────────────────────────────
        mapping_path = self.storage.asset_path(lang, "mapping_rules")
        try:
            rows: List[List[str]] = []
            existing_words: set[str] = set()

            if mapping_path.is_file():
                with mapping_path.open(newline="", encoding="utf-8-sig") as fh:
                    reader = csv.reader(fh)
                    rows = list(reader)
                for row in rows[1:]:
                    if row:
                        existing_words.add(row[0].strip())

            if not rows:
                rows = [["自创语词汇", "IPA音标", "TTS友好拼写"]]

            for entry in entries:
                if entry.conlang and entry.conlang not in existing_words:
                    ipa = entry.ipa or ""
                    tts = entry.tts or entry.conlang
                    rows.append([entry.conlang, ipa, tts])
                    existing_words.add(entry.conlang)

            with mapping_path.open("w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh)
                writer.writerows(rows)
        except Exception as exc:
            errors.append(f"映射表写入失败：{exc}")

        if errors:
            QMessageBox.critical(self, "写入失败", "\n".join(errors))
        else:
            # 刷新内存词库
            report = refresh_materials_from_disk(self.storage, lang)
            self._material_by_lang[lang["id"]] = report.bundle
            self._refresh_list_item_for_language(lang["id"])
            self._refresh_asset_status()
            self.statusBar().showMessage(
                f"已添加 {len(entries)} 个新词到词库，重新翻译可生效", 5000
            )

    # ── 未匹配词处理（阶段七：UnmatchedWordsDialog）─────────────────────

    def _on_add_unmatched_words(self) -> None:
        """打开「未匹配词汇处理」对话框（阶段七升级版），支持手动填写与 AI 生成。"""
        if not self._last_unmatched:
            return
        lang = self.get_current_language()
        if lang is None:
            return

        self._ensure_material_bundle(lang)
        bundle = self._material_by_lang.get(lang["id"], {})
        self._paperhub_settings = load_paperhub_settings(self.storage.base_dir)

        dlg = UnmatchedWordsDialog(
            unmatched_words=self._last_unmatched,
            bundle=bundle,
            paperhub_settings=self._paperhub_settings,
            parent=self,
        )
        if dlg.exec_() == QDialog.Accepted:
            entries = dlg.get_entries()
            filled = [e for e in entries if e.conlang]
            if filled:
                self._write_unmatched_entries_to_lexicon(filled, lang)
                self._last_unmatched = []
                if self._add_word_btn is not None:
                    self._add_word_btn.setVisible(False)
            else:
                self.statusBar().showMessage("没有需要保存的词汇", 3000)

    # ── 批量翻译（预留）───────────────────────────────────────────────

    def _pick_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Excel", str(Path.home()),
            "Excel Files (*.xlsx *.xls);;All Files (*.*)",
        )
        if path:
            self._excel_path = path
            if self.batch_path_display is not None:
                self.batch_path_display.setText(path)
            if self.batch_log is not None:
                self.batch_log.appendPlainText(f"已选择：{path}")

    def _on_batch_start(self) -> None:
        if self.batch_log is not None:
            self.batch_log.appendPlainText("批量翻译将于后续阶段接入。")

    def _on_batch_export(self) -> None:
        if self.batch_log is not None:
            self.batch_log.appendPlainText("导出功能将于后续阶段接入。")

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于 Nikki Conlang Forge",
            "<b>Nikki Conlang Forge</b><br>"
            "无限暖暖自创语翻译器<br><br>"
            "阶段七：未匹配词汇处理（AI辅助）已完成。<br>"
            "支持规则翻译 + PaperHub AI 辅助（三种策略）<br>"
            " + 未匹配词汇对话框（手动填写 / AI 单词生成 /<br>"
            "批量AI生成 / 保存到词库含富元数据）。",
        )