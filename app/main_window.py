from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.app_paths import get_data_dir, get_icon_source_path, get_icon_ico_path
from app.paperhub_settings import DEFAULT_ASK_TEMPLATES, load_ask_templates, save_ask_templates

from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
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
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.asset_validation import check_asset
from app.batch_translate_dialog import BatchTranslateDialog, BatchTranslateSettings
from app.batch_translator import (
    BatchTranslateResult,
    BatchTranslateWorker,
    export_results_to_excel,
    export_unmatched_report,
    generate_timestamp_filename,
)
from app.export_result_dialog import ExportResultDialog
from app.excel_import import (
    ExcelImportResult,
    ExcelRow,
    ExcelStatistics,
    read_excel,
    get_texts_from_rows,
)
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
from app.ipa_generator import generate_ipa_rule
from app.parse_mapping_csv import load_ipa_mapping
from app.rule_translator import RuleTranslationResult, translate_multiline_rule
from app.storage import JsonStorage
from app.ui_theme import UITheme, theme_manager
from app.appearance_dialog import AppearanceDialog

FILE_KEYS = ("whitepaper", "master_library", "mapping_rules", "translation_history")


# ---------------------------------------------------------------------------
# PaperHub 异步翻译线程
# ---------------------------------------------------------------------------

class _PaperHubTranslateThread(QThread):
    """后台线程执行 PaperHub AI 翻译，避免阻塞 UI。"""

    finished = pyqtSignal(object)   # PaperHubResult
    stream_chunk = pyqtSignal(str)  # 流式输出块（逐字追加到输出框）

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
        def _on_chunk(piece: str) -> None:
            self.stream_chunk.emit(piece)

        try:
            result = translate_with_paperhub(
                self._settings, self._bundle, self._text, on_chunk=_on_chunk
            )
        except Exception as exc:
            result = PaperHubResult(error=str(exc))
        self.finished.emit(result)


class _AskChatThread(QThread):
    """后台线程执行 ASK 多轮对话 AI 调用。"""

    finished = pyqtSignal(str, str)     # (full_text, error_message)
    stream_chunk = pyqtSignal(str)      # 流式输出块

    def __init__(
        self,
        settings: Dict[str, Any],
        system_prompt: str,
        messages: List[Dict[str, str]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._system_prompt = system_prompt
        self._messages = messages

    def run(self) -> None:
        from app.paperhub_client import PaperHubError, _make_error_hint

        api_key = str(self._settings.get("paperhub_api_key") or "").strip()
        base_url = str(self._settings.get("paperhub_base_url") or "https://tc-paperhub.diezhi.net/v1")
        model = str(self._settings.get("paperhub_model") or "qwen3-max")
        temperature = float(self._settings.get("paperhub_temperature", 0.7))
        max_tokens = int(self._settings.get("paperhub_max_tokens", 2048))
        reasoning_enabled = bool(self._settings.get("paperhub_reasoning_enabled", False))
        timeout = max(10, int(self._settings.get("paperhub_timeout", 90)))
        stream = bool(self._settings.get("paperhub_stream", True))

        if not api_key:
            self.finished.emit("", "未填写 PaperHub API Key，请在设置中配置。")
            return

        api_messages = [{"role": "system", "content": self._system_prompt}]
        for msg in self._messages:
            api_messages.append({"role": msg["role"], "content": msg["content"]})

        try:
            from openai import OpenAI
        except ImportError:
            self.finished.emit("", "缺少 openai 包，请执行 pip install openai。")
            return

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        create_kwargs = {
            "model": model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if reasoning_enabled:
            create_kwargs["extra_body"] = {"reasoning": {"enabled": True}}

        try:
            if stream:
                create_kwargs["stream"] = True
                accumulated = ""
                for chunk in client.chat.completions.create(**create_kwargs):
                    if not chunk.choices:
                        continue
                    piece = getattr(chunk.choices[0].delta, "content", None) or ""
                    if piece:
                        accumulated += piece
                        self.stream_chunk.emit(piece)
                text = accumulated.strip()
            else:
                resp = client.chat.completions.create(**create_kwargs)
                text = (getattr(resp.choices[0].message, "content", None) or "").strip()

            self.finished.emit(text, "")
        except Exception as exc:
            exc_str = str(exc)
            hint = _make_error_hint(exc_str, model, timeout)
            self.finished.emit("", hint)


class _TokenCircleWidget(QWidget):
    """Token 使用率圆环可视化控件。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._ratio: float = 0.0   # 0.0 ~ 1.0

    def set_ratio(self, ratio: float) -> None:
        """设置使用率（0.0 ~ 1.0），超过 0.8 变红色预警。"""
        self._ratio = max(0.0, min(1.0, ratio))
        self.update()

    def paintEvent(self, event) -> None:
        from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QRadialGradient
        from app.ui_theme import theme_manager

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2
        radius = min(w, h) / 2 - 4
        pen_width = 5

        # 背景环（灰色）
        bg_color = QColor(theme_manager.token("color_border") or "#555555")
        bg_color.setAlpha(160)
        painter.setPen(QPen(bg_color, pen_width))
        painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
        painter.drawArc(
            int(cx - radius), int(cy - radius),
            int(2 * radius), int(2 * radius),
            0, 360 * 16,
        )

        # 进度环
        if self._ratio > 0:
            ratio = self._ratio
            # 颜色：低用量绿色 → 中用量主题色 → 高用量红色
            if ratio < 0.5:
                arc_color = QColor("#4CAF50")     # 绿
            elif ratio < 0.8:
                arc_color = QColor(theme_manager.token("color_primary") or "#2196F3")
            else:
                arc_color = QColor("#F44336")      # 红

            painter.setPen(QPen(arc_color, pen_width, Qt.SolidLine, Qt.RoundCap))
            painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
            start_angle = 90 * 16  # 从顶部开始
            span_angle = -int(ratio * 360 * 16)
            painter.drawArc(
                int(cx - radius), int(cy - radius),
                int(2 * radius), int(2 * radius),
                start_angle, span_angle,
            )

        # 中心文字（百分比）
        pct_text = f"{int(self._ratio * 100)}%"
        from PyQt5.QtGui import QFont
        font = QFont()
        font.setPixelSize(max(10, int(radius * 0.6)))
        font.setBold(True)
        painter.setFont(font)
        text_color = QColor(theme_manager.token("color_text_primary") or "#EEEEEE")
        painter.setPen(QPen(text_color))
        painter.drawText(self.rect(), Qt.AlignCenter, pct_text)

        painter.end()


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Nikki Conlang Forge 主窗口（资料管理 + PaperHub AI 翻译核心）。"""

    def __init__(self) -> None:
        super().__init__()
        self.storage = JsonStorage(get_data_dir())
        self.state = self.storage.load_state()

        self._splitter: Optional[QSplitter] = None
        self._right_tabs: Optional[QTabWidget] = None
        self.language_list: Optional[QListWidget] = None
        self._status_labels: Dict[str, QLabel] = {}
        self._batch_body: Optional[QWidget] = None
        self._batch_toggle_btn: Optional[QPushButton] = None
        self._batch_expanded = False

        self.source_input: Optional[QPlainTextEdit] = None
        self.target_output: Optional[QPlainTextEdit] = None
        self.tts_output: Optional[QPlainTextEdit] = None
        self.ipa_output: Optional[QPlainTextEdit] = None      # 国际音标读音
        self._realtime_output: Optional[QPlainTextEdit] = None  # 实时生成过程
        self.batch_log: Optional[QPlainTextEdit] = None
        self.batch_progress: Optional[QProgressBar] = None
        self.batch_path_display: Optional[QLabel] = None
        self._excel_path: str = ""
        self._excel_import_result: Optional[ExcelImportResult] = None
        self._batch_translate_settings: Optional[BatchTranslateSettings] = None
        self._batch_worker: Optional[BatchTranslateWorker] = None
        self._batch_results: List[BatchTranslateResult] = []

        # AI 翻译进度条（在单句翻译区下方）
        self._ai_progress: Optional[QProgressBar] = None
        self._ai_progress_label: Optional[QLabel] = None

        self._material_by_lang: Dict[str, Dict] = {}
        self._paperhub_settings: Dict = load_paperhub_settings()

        # 翻译统计与未匹配词管理
        self._stats_label: Optional[QLabel] = None
        self._add_word_btn: Optional[QPushButton] = None
        self._last_unmatched: List[str] = []
        self._last_rule_result: Optional[RuleTranslationResult] = None

        # PaperHub AI 翻译线程与状态
        self._ph_thread: Optional[_PaperHubTranslateThread] = None
        self._ph_rule_result: Optional[RuleTranslationResult] = None

        # ASK 页签 — AI 对话模式
        self._ask_chat_display: Optional[QTextEdit] = None
        self._ask_input: Optional[QPlainTextEdit] = None
        self._ask_send_btn: Optional[QPushButton] = None
        self._ask_clear_btn: Optional[QPushButton] = None
        self._ask_token_circle: Optional[QWidget] = None
        self._ask_token_label: Optional[QLabel] = None
        self._ask_pending_panel: Optional[QWidget] = None
        self._ask_pending_table: Optional[QTableWidget] = None
        self._ask_pending_toggle: Optional[QPushButton] = None
        self._ask_batch_confirm_btn: Optional[QPushButton] = None
        self._ask_batch_discard_btn: Optional[QPushButton] = None
        self._ask_confirm_selected_btn: Optional[QPushButton] = None
        self._ask_discard_selected_btn: Optional[QPushButton] = None
        self._ask_templates: List[Dict[str, str]] = load_ask_templates()
        self._ask_template_btns: List[QPushButton] = []
        self._ask_template_row: Optional[QHBoxLayout] = None
        self._ask_messages: List[Dict[str, str]] = []
        self._ask_chat_thread: Optional[_AskChatThread] = None
        self._ask_ai_pending: str = ""
        self._ask_ai_just_started: bool = False
        self._ph_text: str = ""
        self._ph_lang: Optional[Dict] = None
        self._ph_bundle: Dict = {}
        self._ph_lexicon: Dict[str, str] = {}
        self._ph_tts_map: Dict[str, str] = {}

        # ── 设置窗口图标 ─────────────────────────────────────────────
        self._apply_window_icon()

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
        act_appearance = QAction("外观与主题…", self)
        act_appearance.triggered.connect(self._open_appearance_settings)
        tools_menu.addAction(act_appearance)

        help_menu = menubar.addMenu("帮助")
        act_about = QAction("关于", self)
        act_about.triggered.connect(self._show_about)
        help_menu.addAction(act_about)

    # ── 窗口图标 ──────────────────────────────────────────────────────

    def _apply_window_icon(self) -> None:
        """加载 assets/ 目录下的应用图标并设置为窗口图标。

        图标源文件可替换：将新图标放入 assets/app_icon.jpg（或 .png / .ico），
        重启应用即可生效。运行时自动将 jpg/png 转换为 .ico 供 Windows 使用。
        """
        icon_path = get_icon_ico_path()
        if icon_path and str(icon_path):
            icon = QIcon(str(icon_path))
            if not icon.isNull():
                self.setWindowIcon(icon)
        else:
            # ico 不可用时尝试直接加载源文件（jpg/png）
            source_path = get_icon_source_path()
            if source_path and str(source_path):
                icon = QIcon(str(source_path))
                if not icon.isNull():
                    self.setWindowIcon(icon)

    # ── 中央区域 ──────────────────────────────────────────────────────

    def _build_central(self) -> None:
        self.setWindowTitle("Nikki Conlang Forge")
        self.resize(1480, 820)

        self._splitter = QSplitter(Qt.Horizontal)

        left = self._build_left_panel()
        left.setMinimumWidth(160)
        left.resize(200, left.height())

        # 右侧区域使用 QTabWidget 分为「翻译」和「ASK」两个页签
        self._right_tabs = QTabWidget()
        self._right_tabs.setObjectName("cls_right_tabs")
        # 每个 Tab 按文字自然宽度显示（min-width 由 QSS 保证足够空间）
        self._right_tabs.tabBar().setExpanding(False)
        self._right_tabs.tabBar().setUsesScrollButtons(False)

        translate_page = self._build_right_panel()
        ask_page = self._build_ask_page()

        self._right_tabs.addTab(translate_page, "翻译")
        self._right_tabs.addTab(ask_page, "语言大师问答")

        self._splitter.addWidget(left)
        self._splitter.addWidget(self._right_tabs)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([200, 1200])

        self.setCentralWidget(self._splitter)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setProperty("class", "sidebar")
        panel.setObjectName("cls_sidebar")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 语言选择区域（辅色背景）
        lang_selector = QWidget()
        lang_selector.setProperty("class", "lang-selector")

        lang_selector.setObjectName("cls_lang_selector")

        lang_layout = QVBoxLayout(lang_selector)
        lang_layout.setContentsMargins(4, 4, 4, 4)
        lang_layout.setSpacing(4)

        title = QLabel("语言")
        title.setProperty("class", "title")
        title.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        title.setObjectName("cls_title")


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
        assets_title.setProperty("class", "title")
        assets_title.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        assets_title.setObjectName("cls_title")


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
        btn_import.setProperty("class", "highlight")

        btn_import.setObjectName("cls_highlight")

        btn_import.clicked.connect(self.open_import_dialog)

        lang_layout.addWidget(title)
        lang_layout.addWidget(self.language_list, 1)
        lang_layout.addLayout(btn_row)

        # 资料区域（主色浅背景）
        assets_panel = QWidget()
        assets_panel.setProperty("class", "assets-panel")

        assets_panel.setObjectName("cls_assets_panel")

        assets_layout = QVBoxLayout(assets_panel)
        assets_layout.setContentsMargins(4, 4, 4, 4)
        assets_layout.setSpacing(4)

        assets_layout.addStretch(1)
        assets_layout.addWidget(assets_title)
        assets_layout.addWidget(assets_box)
        assets_layout.addWidget(btn_import)
        assets_layout.addStretch(1)

        layout.addWidget(lang_selector, 7)
        layout.addWidget(assets_panel, 3)

        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(12, 12, 12, 12)
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
        btn_copy_src.setProperty("class", "small")

        btn_copy_src.setObjectName("cls_small")

        btn_copy_src.setToolTip("复制中文输入文本")
        src_hdr.addWidget(btn_copy_src)
        io_grid.addLayout(src_hdr, 0, 0)

        # 自创语输出 — 标题行
        con_hdr = QHBoxLayout()
        con_hdr.addWidget(QLabel("自创语输出"))
        con_hdr.addStretch(1)
        btn_copy_con = QPushButton("复制")
        btn_copy_con.setProperty("class", "small")

        btn_copy_con.setObjectName("cls_small")

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
        self._translate_btn.setProperty("class", "primary")

        self._translate_btn.setObjectName("cls_primary")
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
        self._ai_progress_label.setProperty("class", "muted")

        self._ai_progress_label.setObjectName("cls_muted")
        ai_progress_row.addWidget(self._ai_progress_label)
        single_layout.addLayout(ai_progress_row)

        # ── 实时生成过程区 ─────────────────────────────────────────
        realtime_hdr = QHBoxLayout()
        realtime_hdr.addWidget(QLabel("实时生成过程"))
        realtime_hdr.addStretch(1)
        btn_clear_realtime = QPushButton("清空")
        btn_clear_realtime.setProperty("class", "small")
        btn_clear_realtime.setObjectName("cls_small")
        btn_clear_realtime.setToolTip("清空实时生成内容")
        btn_clear_realtime.clicked.connect(self.clear_realtime_generation)
        realtime_hdr.addWidget(btn_clear_realtime)
        single_layout.addLayout(realtime_hdr)

        self._realtime_output = QPlainTextEdit()
        self._realtime_output.setReadOnly(True)
        self._realtime_output.setPlaceholderText(
            "流式翻译时，AI 生成的 token 将实时显示在这里…\n"
            "非流式模式下保持为空。"
        )
        self._realtime_output.setMaximumHeight(100)
        single_layout.addWidget(self._realtime_output)

        # ── TTS 音译 + 国际音标读音 并排 ────────────────────────────
        phonetics_row = QHBoxLayout()
        phonetics_row.setSpacing(6)

        # 左：TTS 音译
        tts_col = QVBoxLayout()
        tts_col.setSpacing(3)
        tts_hdr = QHBoxLayout()
        tts_hdr.addWidget(QLabel("TTS 音译"))
        tts_hdr.addStretch(1)
        btn_copy_tts = QPushButton("复制")
        btn_copy_tts.setProperty("class", "small")
        btn_copy_tts.setObjectName("cls_small")
        btn_copy_tts.setToolTip("复制 TTS 友好音译")
        tts_hdr.addWidget(btn_copy_tts)
        tts_col.addLayout(tts_hdr)
        self.tts_output = QPlainTextEdit()
        self.tts_output.setReadOnly(True)
        self.tts_output.setPlaceholderText("TTS 友好音译（供语音合成使用）")
        self.tts_output.setMaximumHeight(90)
        tts_col.addWidget(self.tts_output)
        phonetics_row.addLayout(tts_col, 1)

        # 右：国际音标读音
        ipa_col = QVBoxLayout()
        ipa_col.setSpacing(3)
        ipa_hdr = QHBoxLayout()
        ipa_hdr.addWidget(QLabel("国际音标读音"))
        ipa_hdr.addStretch(1)
        btn_copy_ipa = QPushButton("复制")
        btn_copy_ipa.setProperty("class", "small")
        btn_copy_ipa.setObjectName("cls_small")
        btn_copy_ipa.setToolTip("复制国际音标读音")
        ipa_hdr.addWidget(btn_copy_ipa)
        ipa_col.addLayout(ipa_hdr)
        self.ipa_output = QPlainTextEdit()
        self.ipa_output.setReadOnly(True)
        self.ipa_output.setPlaceholderText("国际音标（IPA）待生成")
        self.ipa_output.setMaximumHeight(90)
        ipa_col.addWidget(self.ipa_output)
        phonetics_row.addLayout(ipa_col, 1)

        single_layout.addLayout(phonetics_row)

        # 统计行
        stats_row = QHBoxLayout()
        self._stats_label = QLabel("")
        self._stats_label.setProperty("class", "secondary")

        self._stats_label.setObjectName("cls_secondary")
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
        btn_copy_ipa.clicked.connect(
            lambda: QApplication.clipboard().setText(
                self.ipa_output.toPlainText() if self.ipa_output else ""
            )
        )

        # 输入框清空时同步清空输出
        if self.source_input is not None:
            self.source_input.textChanged.connect(self._on_source_input_text_changed)

        outer.addWidget(single, 1)

        # ── 批量翻译区（可折叠） ────────────────────────────────────
        batch_wrap = QWidget()
        batch_outer = QVBoxLayout(batch_wrap)
        batch_outer.setContentsMargins(0, 0, 0, 0)
        batch_outer.setSpacing(4)

        self._batch_toggle_btn = QPushButton("批量翻译  ▶")
        self._batch_toggle_btn.setProperty("class", "toggle-btn")

        self._batch_toggle_btn.setObjectName("cls_toggle_btn")
        self._batch_toggle_btn.clicked.connect(self._toggle_batch_section)

        self._batch_body = QWidget()
        batch_layout = QVBoxLayout(self._batch_body)
        batch_layout.setSpacing(8)

        batch_box = QGroupBox("批量翻译")
        inner = QVBoxLayout(batch_box)

        btn_row2 = QHBoxLayout()
        btn_pick = QPushButton("选择 Excel")
        btn_pick.clicked.connect(self._pick_excel)
        self._btn_batch_start = QPushButton("开始翻译")
        self._btn_batch_start.clicked.connect(self._on_batch_start)
        self._btn_batch_pause = QPushButton("暂停")
        self._btn_batch_pause.clicked.connect(self._on_batch_pause_resume)
        self._btn_batch_pause.setVisible(False)
        self._btn_batch_cancel = QPushButton("取消")
        self._btn_batch_cancel.clicked.connect(self._on_batch_cancel)
        self._btn_batch_cancel.setVisible(False)
        btn_export = QPushButton("导出文件")
        btn_export.clicked.connect(self._on_batch_export)
        btn_row2.addWidget(btn_pick)
        btn_row2.addWidget(self._btn_batch_start)
        btn_row2.addWidget(self._btn_batch_pause)
        btn_row2.addWidget(self._btn_batch_cancel)
        btn_row2.addWidget(btn_export)
        btn_row2.addStretch(1)

        self.batch_path_display = QLabel("未选择文件")
        self.batch_path_display.setWordWrap(True)
        self.batch_path_display.setProperty("class", "muted")

        self.batch_path_display.setObjectName("cls_muted")

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

    # ── ASK 页签 ─────────────────────────────────────────────────────

    def _build_ask_page(self) -> QWidget:
        """构建 ASK 页签（AI 对话模式）— 上中下三区可拉伸布局。"""
        page = QWidget()
        page.setObjectName("cls_ask_page")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(12, 12, 12, 12)
        page_layout.setSpacing(0)

        # ── 垂直分割器：上(对话) → 中(待审核) → 下(提问) ────────
        v_splitter = QSplitter(Qt.Vertical)
        v_splitter.setObjectName("cls_ask_v_splitter")

        # ── 上区：对话历史 ────────────────────────────────────────
        chat_wrap = QWidget()
        chat_layout = QVBoxLayout(chat_wrap)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(4)

        chat_hdr = QHBoxLayout()
        chat_hdr.addWidget(QLabel("对话历史"))
        chat_hdr.addStretch(1)
        self._ask_clear_btn = QPushButton("清空对话")
        self._ask_clear_btn.setProperty("class", "small")
        self._ask_clear_btn.setObjectName("cls_small")
        self._ask_clear_btn.clicked.connect(self._ask_clear_conversation)
        chat_hdr.addWidget(self._ask_clear_btn)
        chat_layout.addLayout(chat_hdr)

        self._ask_chat_display = QTextEdit()
        self._ask_chat_display.setReadOnly(True)
        self._ask_chat_display.setObjectName("cls_ask_chat_display")
        self._ask_chat_display.setProperty("class", "chat-display")
        self._ask_chat_display.setPlaceholderText(
            "在这里与 AI 进行对话，探讨翻译方案、词库创作…"
        )
        chat_layout.addWidget(self._ask_chat_display, 1)

        # Token 圆圈 + 数量标签
        token_row = QHBoxLayout()
        token_row.setSpacing(6)
        self._ask_token_circle = _TokenCircleWidget()
        self._ask_token_circle.setFixedSize(48, 48)
        self._ask_token_circle.setObjectName("cls_ask_token_circle")
        self._ask_token_label = QLabel("— / —")
        self._ask_token_label.setProperty("class", "muted")
        self._ask_token_label.setObjectName("cls_muted")
        self._ask_token_label.setToolTip("当前 Token 用量 / 模型上下文上限")
        token_row.addWidget(self._ask_token_circle)
        token_row.addWidget(self._ask_token_label)
        token_row.addStretch(1)
        chat_layout.addLayout(token_row)

        v_splitter.addWidget(chat_wrap)

        # ── 中区：待审核候选词 ────────────────────────────────────
        pending_wrap = QWidget()
        pending_layout = QVBoxLayout(pending_wrap)
        pending_layout.setContentsMargins(0, 0, 0, 0)
        pending_layout.setSpacing(4)

        pending_hdr = QHBoxLayout()
        pending_hdr.addWidget(QLabel("待审核候选词"))
        pending_hdr.addStretch(1)

        self._ask_pending_toggle = QPushButton("收起  ▼")
        self._ask_pending_toggle.setProperty("class", "small")
        self._ask_pending_toggle.setObjectName("cls_small")
        self._ask_pending_toggle.clicked.connect(self._toggle_ask_pending)
        pending_hdr.addWidget(self._ask_pending_toggle)

        self._ask_batch_confirm_btn = QPushButton("全部确认")
        self._ask_batch_confirm_btn.setProperty("class", "primary")
        self._ask_batch_confirm_btn.setObjectName("cls_primary")
        self._ask_batch_confirm_btn.clicked.connect(self._ask_batch_confirm_pending)
        self._ask_batch_confirm_btn.setVisible(False)
        pending_hdr.addWidget(self._ask_batch_confirm_btn)

        self._ask_batch_discard_btn = QPushButton("全部丢弃")
        self._ask_batch_discard_btn.setProperty("class", "small")
        self._ask_batch_discard_btn.setObjectName("cls_small")
        self._ask_batch_discard_btn.clicked.connect(self._ask_batch_discard_pending)
        self._ask_batch_discard_btn.setVisible(False)
        pending_hdr.addWidget(self._ask_batch_discard_btn)

        self._ask_confirm_selected_btn = QPushButton("确认选中")
        self._ask_confirm_selected_btn.setProperty("class", "primary")
        self._ask_confirm_selected_btn.setObjectName("cls_primary")
        self._ask_confirm_selected_btn.clicked.connect(self._ask_confirm_selected_pending)
        self._ask_confirm_selected_btn.setVisible(False)
        pending_hdr.addWidget(self._ask_confirm_selected_btn)

        self._ask_discard_selected_btn = QPushButton("丢弃选中")
        self._ask_discard_selected_btn.setProperty("class", "small")
        self._ask_discard_selected_btn.setObjectName("cls_small")
        self._ask_discard_selected_btn.clicked.connect(self._ask_discard_selected_pending)
        self._ask_discard_selected_btn.setVisible(False)
        pending_hdr.addWidget(self._ask_discard_selected_btn)

        pending_layout.addLayout(pending_hdr)

        self._ask_pending_table = QTableWidget(0, 6)
        self._ask_pending_table.setObjectName("cls_ask_pending_table")
        self._ask_pending_table.setHorizontalHeaderLabels(
            ["自创语", "IPA", "TTS", "含义", "风格标签", "操作"]
        )
        self._ask_pending_table.horizontalHeader().setStretchLastSection(True)
        self._ask_pending_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._ask_pending_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self._ask_pending_table.setEditTriggers(QTableWidget.NoEditTriggers)
        pending_layout.addWidget(self._ask_pending_table, 1)

        self._ask_pending_panel = pending_wrap
        v_splitter.addWidget(pending_wrap)

        # ── 下区：提问输入区 ──────────────────────────────────────
        input_wrap = QWidget()
        input_layout = QVBoxLayout(input_wrap)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(4)

        # 快捷提问模板按钮行（动态构建）
        template_row = QHBoxLayout()
        template_row.setSpacing(4)
        self._ask_template_row = template_row
        input_layout.addLayout(template_row)
        self._rebuild_template_buttons()

        # 输入框 + 发送按钮
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self._ask_input = QPlainTextEdit()
        self._ask_input.setPlaceholderText("输入你的问题，按发送或 Ctrl+Enter 提交…")
        self._ask_input.setMaximumHeight(80)
        self._ask_input.setObjectName("cls_ask_input")
        self._ask_input.keyPressEvent = self._ask_input_key_event
        input_row.addWidget(self._ask_input, 1)

        self._ask_send_btn = QPushButton("发送")
        self._ask_send_btn.setProperty("class", "primary")
        self._ask_send_btn.setObjectName("cls_primary")
        self._ask_send_btn.setMinimumWidth(72)
        self._ask_send_btn.clicked.connect(self._ask_send_message)
        input_row.addWidget(self._ask_send_btn)

        input_layout.addLayout(input_row)

        v_splitter.addWidget(input_wrap)

        # 默认比例：对话区 60% / 待审核 20% / 输入区 20%
        v_splitter.setStretchFactor(0, 3)
        v_splitter.setStretchFactor(1, 1)
        v_splitter.setStretchFactor(2, 1)
        v_splitter.setSizes([400, 130, 130])

        page_layout.addWidget(v_splitter, 1)

        return page

    # ── 辅助方法 ──────────────────────────────────────────────────────

    def _clear_all_outputs(self) -> None:
        """清空所有输入和输出区域。"""
        if self.source_input is not None:
            self.source_input.clear()
        if self.target_output is not None:
            self.target_output.clear()
        if self.tts_output is not None:
            self.tts_output.clear()
        self.clear_realtime_generation()
        self.clear_ipa_output()
        if self._stats_label is not None:
            self._stats_label.setText("")
        if self._add_word_btn is not None:
            self._add_word_btn.setVisible(False)
        self._last_unmatched = []

    def _on_source_input_text_changed(self) -> None:
        """当中文输入框文本变化时，如果全部清空则同步清空所有输出区域。"""
        if self.source_input is None:
            return
        text = self.source_input.toPlainText()
        if not text.strip():
            if self.target_output is not None:
                self.target_output.clear()
            if self.tts_output is not None:
                self.tts_output.clear()
            self.clear_realtime_generation()
            self.clear_ipa_output()
            if self._stats_label is not None:
                self._stats_label.setText("")
            if self._add_word_btn is not None:
                self._add_word_btn.setVisible(False)
            self._last_unmatched = []

    # ── ASK 页签交互方法（后续步骤完善） ───────────────────────────

    def _ask_clear_conversation(self) -> None:
        """清空 ASK 对话历史和 Token 计数。"""
        self._ask_messages.clear()
        if self._ask_chat_display is not None:
            self._ask_chat_display.clear()
        self._ask_update_token_display()

    def _ask_send_message(self) -> None:
        """发送用户提问，触发 AI 多轮对话。"""
        if self._ask_input is None or self._ask_send_btn is None:
            return
        # 如果 AI 正在回复，不允许再次发送
        if self._ask_chat_thread is not None and self._ask_chat_thread.isRunning():
            return

        user_text = self._ask_input.toPlainText().strip()
        if not user_text:
            return

        # 追加用户消息
        self._ask_append_chat_message("user", user_text)
        self._ask_messages.append({"role": "user", "content": user_text})
        self._ask_input.clear()
        self._ask_update_token_display()

        # 重新加载 PaperHub 设置（用户可能刚改过配置）
        self._paperhub_settings = load_paperhub_settings()
        settings = self._paperhub_settings

        if not settings.get("paperhub_enabled", False):
            self._ask_append_chat_message("system",
                "⚠ PaperHub AI 未启用，请在「设置 → PaperHub 设置」中开启。")
            return

        api_key = str(settings.get("paperhub_api_key") or "").strip()
        if not api_key:
            self._ask_append_chat_message("system",
                "⚠ 未填写 PaperHub API Key，请在「设置 → PaperHub 设置」中配置。")
            return

        # 构建 ASK 系统提示词 — 使用当前选中语言的资料（而非翻译页签缓存的 _ph_bundle）
        lang = self.get_current_language()
        if lang is None:
            self._ask_append_chat_message("system",
                "⚠ 请先在左侧面板选择一种语言。")
            return
        self._ensure_material_bundle(lang)
        bundle = self._material_by_lang.get(lang.get("id", ""), {})
        self._ph_lang = lang
        self._ph_bundle = bundle
        system_prompt = self._build_ask_system_prompt(bundle)

        # 禁用发送按钮
        self._ask_send_btn.setEnabled(False)
        self._ask_send_btn.setText("思考中…")
        self._ask_ai_pending = ""
        self._ask_ai_just_started = True

        # 启动后台线程
        self._ask_chat_thread = _AskChatThread(
            settings=settings,
            system_prompt=system_prompt,
            messages=self._ask_messages,
        )
        self._ask_chat_thread.stream_chunk.connect(self._ask_on_stream_chunk)
        self._ask_chat_thread.finished.connect(self._ask_on_chat_finished)
        self._ask_chat_thread.start()

    def _ask_on_stream_chunk(self, piece: str) -> None:
        """流式接收 AI 响应块，实时追加到对话区。"""
        if self._ask_chat_display is None:
            return
        self._ask_ai_pending += piece

        if self._ask_ai_just_started:
            # 首次收到 chunk：插入 AI 标签
            color_ai = theme_manager.token("color_primary")
            self._ask_chat_display.append(
                f'<p style="margin:4px 0;"><b style="color:{color_ai};">AI：</b>'
            )
            self._ask_ai_just_started = False

        # 追加文本块（使用 QTextEdit 的 insertPlainText 以保持纯文本追加）
        cursor = self._ask_chat_display.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText(piece)
        self._ask_chat_display.setTextCursor(cursor)
        self._ask_chat_display.ensureCursorVisible()

    def _ask_on_chat_finished(self, full_text: str, error: str) -> None:
        """AI 对话完成：追加完整 AI 消息到对话历史。"""
        # 恢复发送按钮
        if self._ask_send_btn is not None:
            self._ask_send_btn.setEnabled(True)
            self._ask_send_btn.setText("发送")

        if error:
            self._ask_append_chat_message("system", f"⚠ {error}")
            return

        # 如果有流式输出，_ask_ai_pending 已包含完整文本
        # 否则用 full_text
        ai_text = self._ask_ai_pending if self._ask_ai_pending else full_text

        if not ai_text.strip():
            self._ask_append_chat_message("system", "AI 返回了空内容。")
            return

        # 追加 AI 消息到对话记录
        self._ask_messages.append({"role": "assistant", "content": ai_text})
        self._ask_update_token_display()

        # 如果不是流式模式，需要手动追加显示
        if not self._ask_ai_pending:
            self._ask_append_chat_message("ai", ai_text)

        # 第 6 步会在这里解析候选词
        self._ask_parse_ai_response(ai_text)

        self._ask_ai_pending = ""

    def _build_ask_system_prompt(self, bundle: Dict[str, Any]) -> str:
        """构建 ASK 对话模式的系统提示词。"""
        from app.paperhub_client import _whitepaper_full, _vocabulary_list

        lang_name = ""
        lang = self._ph_lang
        if lang and isinstance(lang, dict):
            lang_name = lang.get("name", "")

        wp = _whitepaper_full(bundle)
        vocab = _vocabulary_list(bundle, max_items=120)

        return (
            "你是一个虚构语言翻译专家和创作顾问。"
            f"当前语言是「{lang_name}」。"
            "你可以与用户自由对话，讨论翻译方案、词源创作、风格变体等。\n"
            "【重要规则】\n"
            "- 优先使用词库中已有的词汇\n"
            "- 创造新词时请提供：自创语形式、IPA音标、TTS拼写、含义、风格标签\n"
            "- 新词请用如下格式输出以便系统自动提取：\n"
            "  【新词】自创语|IPA|TTS|含义|风格标签\n"
            "- 可以自然地解释构词逻辑和音系来源\n"
            "- 保持活泼有趣的对话风格\n"
            f"\n【语言白皮书】\n{wp}\n"
            f"\n【词库】\n{vocab}\n"
        )

    def _ask_parse_ai_response(self, ai_text: str) -> None:
        """解析 AI 响应中的候选词，添加到待审核表格（第 6 步完善）。"""
        # 提取 【新词】xxx|IPA|TTS|含义|风格标签 格式的候选词
        import re
        pattern = r"【新词】(.+?)\|(.+?)\|(.+?)\|(.+?)\|(.+)"
        matches = re.findall(pattern, ai_text)
        if not matches:
            return
        for m in matches:
            conlang, ipa, tts, meaning, tags = m
            self._ask_add_pending_row(conlang.strip(), ipa.strip(), tts.strip(), meaning.strip(), tags.strip())
        # 显示批量操作按钮
        if self._ask_batch_confirm_btn is not None:
            self._ask_batch_confirm_btn.setVisible(True)
        if self._ask_batch_discard_btn is not None:
            self._ask_batch_discard_btn.setVisible(True)
        if self._ask_confirm_selected_btn is not None:
            self._ask_confirm_selected_btn.setVisible(True)
        if self._ask_discard_selected_btn is not None:
            self._ask_discard_selected_btn.setVisible(True)

    def _ask_input_key_event(self, event) -> None:
        """拦截 Ctrl+Enter 发送消息，其余按键正常传递。"""
        from PyQt5.QtCore import Qt as QtConst
        if event.key() in (QtConst.Key_Return, QtConst.Key_Enter) and (
            event.modifiers() & QtConst.ControlModifier
        ):
            self._ask_send_message()
        else:
            QPlainTextEdit.keyPressEvent(self._ask_input, event)

    def _rebuild_template_buttons(self) -> None:
        """根据 self._ask_templates 重新构建快捷提问按钮行。"""
        if self._ask_template_row is None:
            return
        # 清除旧按钮
        self._ask_template_btns.clear()
        while self._ask_template_row.count():
            item = self._ask_template_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        label = QLabel("快捷提问：")
        self._ask_template_row.addWidget(label)

        for tpl in self._ask_templates:
            btn = QPushButton(tpl["name"])
            btn.setProperty("class", "pill")
            btn.setObjectName("cls_pill")
            btn.setToolTip(tpl["prompt"])
            btn.clicked.connect(self._ask_on_template_clicked)
            self._ask_template_btns.append(btn)
            self._ask_template_row.addWidget(btn)

        # 管理模板按钮
        manage_btn = QPushButton("管理模板…")
        manage_btn.setProperty("class", "pill")
        manage_btn.setObjectName("cls_pill")
        manage_btn.clicked.connect(self._ask_manage_templates)
        self._ask_template_btns.append(manage_btn)
        self._ask_template_row.addWidget(manage_btn)

        self._ask_template_row.addStretch(1)

    def _ask_on_template_clicked(self) -> None:
        """快捷提问模板按钮点击 — 将模板 prompt 文本填入输入框。"""
        if self._ask_input is None:
            return
        sender = self.sender()
        if sender and isinstance(sender, QPushButton):
            name = sender.text()
            # 查找对应的模板 prompt
            for tpl in self._ask_templates:
                if tpl["name"] == name:
                    self._ask_input.setPlainText(tpl["prompt"])
                    self._ask_input.setFocus()
                    return

    def _ask_manage_templates(self) -> None:
        """打开模板管理对话框，允许用户增删改快捷提问模板。"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QListWidget, QHBoxLayout

        dlg = QDialog(self)
        dlg.setWindowTitle("管理快捷提问模板")
        dlg.setMinimumSize(480, 360)
        dlg.setObjectName("cls_ask_template_dialog")
        layout = QVBoxLayout(dlg)

        # 列表
        list_widget = QListWidget()
        list_widget.setObjectName("cls_ask_template_list")
        templates_copy = [dict(t) for t in self._ask_templates]
        for tpl in templates_copy:
            list_widget.addItem(f"{tpl['name']}  ─  {tpl['prompt']}")
        layout.addWidget(list_widget, 1)

        # 操作按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        add_btn = QPushButton("新增")
        add_btn.setProperty("class", "primary")
        add_btn.setObjectName("cls_primary")
        btn_row.addWidget(add_btn)

        edit_btn = QPushButton("编辑")
        edit_btn.setProperty("class", "small")
        edit_btn.setObjectName("cls_small")
        btn_row.addWidget(edit_btn)

        del_btn = QPushButton("删除")
        del_btn.setProperty("class", "small")
        del_btn.setObjectName("cls_small")
        btn_row.addWidget(del_btn)

        layout.addLayout(btn_row)

        # 确认/取消
        confirm_row = QHBoxLayout()
        confirm_row.addStretch(1)
        ok_btn = QPushButton("确定")
        ok_btn.setProperty("class", "primary")
        ok_btn.setObjectName("cls_primary")
        cancel_btn = QPushButton("取消")
        cancel_btn.setProperty("class", "small")
        cancel_btn.setObjectName("cls_small")
        confirm_row.addWidget(ok_btn)
        confirm_row.addWidget(cancel_btn)
        layout.addLayout(confirm_row)

        # ── 按钮逻辑 ──
        def _add_template():
            name, ok = QInputDialog.getText(dlg, "新增模板", "模板名称：")
            if not ok or not name.strip():
                return
            prompt, ok2 = QInputDialog.getText(dlg, "新增模板", "提问文本：")
            if not ok2 or not prompt.strip():
                return
            templates_copy.append({"name": name.strip(), "prompt": prompt.strip()})
            list_widget.addItem(f"{name.strip()}  ─  {prompt.strip()}")

        def _edit_template():
            idx = list_widget.currentRow()
            if idx < 0:
                return
            old = templates_copy[idx]
            name, ok = QInputDialog.getText(dlg, "编辑模板", "模板名称：", text=old["name"])
            if not ok or not name.strip():
                return
            prompt, ok2 = QInputDialog.getText(dlg, "编辑模板", "提问文本：", text=old["prompt"])
            if not ok2 or not prompt.strip():
                return
            templates_copy[idx] = {"name": name.strip(), "prompt": prompt.strip()}
            list_widget.item(idx).setText(f"{name.strip()}  ─  {prompt.strip()}")

        def _del_template():
            idx = list_widget.currentRow()
            if idx < 0:
                return
            templates_copy.pop(idx)
            list_widget.takeItem(idx)

        add_btn.clicked.connect(_add_template)
        edit_btn.clicked.connect(_edit_template)
        del_btn.clicked.connect(_del_template)
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)

        if dlg.exec_() == QDialog.Accepted:
            self._ask_templates = templates_copy
            save_ask_templates(templates_copy)
            self._rebuild_template_buttons()

    def _toggle_ask_pending(self) -> None:
        """折叠/展开待审核候选词面板。"""
        if self._ask_pending_table is None:
            return
        visible = self._ask_pending_table.isVisible()
        self._ask_pending_table.setVisible(not visible)
        if self._ask_pending_toggle is not None:
            self._ask_pending_toggle.setText(
                "收起  ▼" if not visible else "展开  ▶"
            )

    def _ask_batch_confirm_pending(self) -> None:
        """批量确认所有待审核候选词，导入词库。"""
        if self._ask_pending_table is None:
            return
        lang = self._ph_lang
        if not lang or not isinstance(lang, dict):
            QMessageBox.warning(self, "提示", "请先选择一种语言。")
            return

        new_words: List[NewWord] = []
        for row in range(self._ask_pending_table.rowCount()):
            conlang_item = self._ask_pending_table.item(row, 0)
            ipa_item = self._ask_pending_table.item(row, 1)
            tts_item = self._ask_pending_table.item(row, 2)
            meaning_item = self._ask_pending_table.item(row, 3)
            tags_item = self._ask_pending_table.item(row, 4)

            nw = NewWord(
                chinese=meaning_item.text().strip() if meaning_item else "",
                conlang=conlang_item.text().strip() if conlang_item else "",
                ipa=ipa_item.text().strip() if ipa_item else "",
                tts=tts_item.text().strip() if tts_item else "",
                logic=tags_item.text().strip() if tags_item else "",
            )
            if nw.chinese and nw.conlang:
                new_words.append(nw)

        if not new_words:
            return

        self._write_new_words_to_lexicon(new_words, lang)
        self._ask_clear_pending_table()
        self._ask_append_chat_message("system", f"✅ {len(new_words)} 个候选词已确认导入词库。")

    def _ask_batch_discard_pending(self) -> None:
        """批量丢弃所有待审核候选词。"""
        if self._ask_pending_table is None:
            return
        count = self._ask_pending_table.rowCount()
        if count == 0:
            return
        reply = QMessageBox.question(
            self, "丢弃确认",
            f"确定丢弃全部 {count} 个候选词？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._ask_clear_pending_table()
        self._ask_append_chat_message("system", f"🗑 已丢弃 {count} 个候选词。")

    def _ask_clear_pending_table(self) -> None:
        """清空待审核表格并隐藏批量操作按钮。"""
        if self._ask_pending_table is not None:
            self._ask_pending_table.setRowCount(0)
        if self._ask_batch_confirm_btn is not None:
            self._ask_batch_confirm_btn.setVisible(False)
        if self._ask_batch_discard_btn is not None:
            self._ask_batch_discard_btn.setVisible(False)
        if self._ask_confirm_selected_btn is not None:
            self._ask_confirm_selected_btn.setVisible(False)
        if self._ask_discard_selected_btn is not None:
            self._ask_discard_selected_btn.setVisible(False)

    def _ask_add_pending_row(
        self, conlang: str, ipa: str, tts: str, meaning: str, tags: str
    ) -> None:
        """向待审核表格添加一行候选词，并在「操作」列放置 ✓确认 / ✗丢弃 按钮。"""
        if self._ask_pending_table is None:
            return
        row = self._ask_pending_table.rowCount()
        self._ask_pending_table.insertRow(row)
        self._ask_pending_table.setItem(row, 0, QTableWidgetItem(conlang))
        self._ask_pending_table.setItem(row, 1, QTableWidgetItem(ipa))
        self._ask_pending_table.setItem(row, 2, QTableWidgetItem(tts))
        self._ask_pending_table.setItem(row, 3, QTableWidgetItem(meaning))
        self._ask_pending_table.setItem(row, 4, QTableWidgetItem(tags))

        # 操作列：✓确认 + ✗丢弃 按钮
        op_widget = QWidget()
        op_layout = QHBoxLayout(op_widget)
        op_layout.setContentsMargins(2, 2, 2, 2)
        op_layout.setSpacing(4)

        btn_confirm = QPushButton("✓")
        btn_confirm.setProperty("class", "primary")
        btn_confirm.setObjectName("cls_primary")
        btn_confirm.setFixedSize(28, 24)
        btn_confirm.setToolTip("确认导入此词")
        btn_confirm.clicked.connect(lambda _, r=row: self._ask_confirm_single_pending(r))

        btn_discard = QPushButton("✗")
        btn_discard.setProperty("class", "small")
        btn_discard.setObjectName("cls_small")
        btn_discard.setFixedSize(28, 24)
        btn_discard.setToolTip("丢弃此词")
        btn_discard.clicked.connect(lambda _, r=row: self._ask_discard_single_pending(r))

        op_layout.addWidget(btn_confirm)
        op_layout.addWidget(btn_discard)
        op_widget.setLayout(op_layout)
        self._ask_pending_table.setCellWidget(row, 5, op_widget)

    def _ask_confirm_single_pending(self, row: int) -> None:
        """确认导入单条候选词到词库。"""
        if self._ask_pending_table is None:
            return
        if row < 0 or row >= self._ask_pending_table.rowCount():
            return

        lang = self._ph_lang
        if not lang or not isinstance(lang, dict):
            QMessageBox.warning(self, "提示", "请先选择一种语言。")
            return

        conlang_item = self._ask_pending_table.item(row, 0)
        ipa_item = self._ask_pending_table.item(row, 1)
        tts_item = self._ask_pending_table.item(row, 2)
        meaning_item = self._ask_pending_table.item(row, 3)
        tags_item = self._ask_pending_table.item(row, 4)

        nw = NewWord(
            chinese=meaning_item.text().strip() if meaning_item else "",
            conlang=conlang_item.text().strip() if conlang_item else "",
            ipa=ipa_item.text().strip() if ipa_item else "",
            tts=tts_item.text().strip() if tts_item else "",
            logic=tags_item.text().strip() if tags_item else "",
        )
        if nw.chinese and nw.conlang:
            self._write_new_words_to_lexicon([nw], lang)

        self._ask_pending_table.removeRow(row)
        # 按钮的 row 引用的是旧行号，移除后后续行的按钮 row 需要更新
        self._ask_refresh_pending_row_buttons()
        self._ask_append_chat_message("system", f"✅ 候选词「{nw.chinese} → {nw.conlang}」已确认导入词库。")

        # 如果表格清空，隐藏按钮
        if self._ask_pending_table.rowCount() == 0:
            self._ask_clear_pending_table()

    def _ask_discard_single_pending(self, row: int) -> None:
        """丢弃单条候选词。"""
        if self._ask_pending_table is None:
            return
        if row < 0 or row >= self._ask_pending_table.rowCount():
            return

        meaning_item = self._ask_pending_table.item(row, 3)
        conlang_item = self._ask_pending_table.item(row, 0)
        label = f"{meaning_item.text() if meaning_item else ''} → {conlang_item.text() if conlang_item else ''}"

        self._ask_pending_table.removeRow(row)
        self._ask_refresh_pending_row_buttons()
        self._ask_append_chat_message("system", f"🗑 已丢弃候选词「{label}」。")

        if self._ask_pending_table.rowCount() == 0:
            self._ask_clear_pending_table()

    def _ask_confirm_selected_pending(self) -> None:
        """确认导入选中行的候选词到词库。"""
        if self._ask_pending_table is None:
            return
        lang = self._ph_lang
        if not lang or not isinstance(lang, dict):
            QMessageBox.warning(self, "提示", "请先选择一种语言。")
            return

        selected_rows = sorted(
            set(idx.row() for idx in self._ask_pending_table.selectedIndexes()),
            reverse=True
        )
        if not selected_rows:
            self.statusBar().showMessage("请先在表格中选择要确认的候选词", 3000)
            return

        new_words: List[NewWord] = []
        for row in selected_rows:
            conlang_item = self._ask_pending_table.item(row, 0)
            ipa_item = self._ask_pending_table.item(row, 1)
            tts_item = self._ask_pending_table.item(row, 2)
            meaning_item = self._ask_pending_table.item(row, 3)
            tags_item = self._ask_pending_table.item(row, 4)

            nw = NewWord(
                chinese=meaning_item.text().strip() if meaning_item else "",
                conlang=conlang_item.text().strip() if conlang_item else "",
                ipa=ipa_item.text().strip() if ipa_item else "",
                tts=tts_item.text().strip() if tts_item else "",
                logic=tags_item.text().strip() if tags_item else "",
            )
            if nw.chinese and nw.conlang:
                new_words.append(nw)

        if new_words:
            self._write_new_words_to_lexicon(new_words, lang)

        # 从表格移除选中行（倒序移除以保持索引正确）
        for row in selected_rows:
            self._ask_pending_table.removeRow(row)
        self._ask_refresh_pending_row_buttons()
        self._ask_append_chat_message("system", f"✅ {len(new_words)} 个选中候选词已确认导入词库。")

        if self._ask_pending_table.rowCount() == 0:
            self._ask_clear_pending_table()

    def _ask_discard_selected_pending(self) -> None:
        """丢弃选中行的候选词。"""
        if self._ask_pending_table is None:
            return
        selected_rows = sorted(
            set(idx.row() for idx in self._ask_pending_table.selectedIndexes()),
            reverse=True
        )
        if not selected_rows:
            self.statusBar().showMessage("请先在表格中选择要丢弃的候选词", 3000)
            return

        count = len(selected_rows)
        reply = QMessageBox.question(
            self, "丢弃确认",
            f"确定丢弃选中的 {count} 个候选词？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        for row in selected_rows:
            self._ask_pending_table.removeRow(row)
        self._ask_refresh_pending_row_buttons()
        self._ask_append_chat_message("system", f"🗑 已丢弃 {count} 个选中候选词。")

        if self._ask_pending_table.rowCount() == 0:
            self._ask_clear_pending_table()

    def _ask_refresh_pending_row_buttons(self) -> None:
        """移除行后重新绑定每行操作按钮的 row 参数，确保索引正确。"""
        if self._ask_pending_table is None:
            return
        for row in range(self._ask_pending_table.rowCount()):
            op_widget = self._ask_pending_table.cellWidget(row, 5)
            if op_widget is None:
                # 如果该行没有操作按钮（旧数据），重新添加
                self._ask_rebuild_row_buttons(row)
                continue
            btns = op_widget.findChildren(QPushButton)
            for btn in btns:
                # 断开旧连接，重新绑定当前行号
                btn.clicked.disconnect()
                if btn.toolTip().startswith("确认"):
                    btn.clicked.connect(lambda _, r=row: self._ask_confirm_single_pending(r))
                else:
                    btn.clicked.connect(lambda _, r=row: self._ask_discard_single_pending(r))

    def _ask_rebuild_row_buttons(self, row: int) -> None:
        """为没有操作按钮的已有行重新创建按钮 widget。"""
        if self._ask_pending_table is None:
            return
        op_widget = QWidget()
        op_layout = QHBoxLayout(op_widget)
        op_layout.setContentsMargins(2, 2, 2, 2)
        op_layout.setSpacing(4)

        btn_confirm = QPushButton("✓")
        btn_confirm.setProperty("class", "primary")
        btn_confirm.setObjectName("cls_primary")
        btn_confirm.setFixedSize(28, 24)
        btn_confirm.setToolTip("确认导入此词")
        btn_confirm.clicked.connect(lambda _, r=row: self._ask_confirm_single_pending(r))

        btn_discard = QPushButton("✗")
        btn_discard.setProperty("class", "small")
        btn_discard.setObjectName("cls_small")
        btn_discard.setFixedSize(28, 24)
        btn_discard.setToolTip("丢弃此词")
        btn_discard.clicked.connect(lambda _, r=row: self._ask_discard_single_pending(r))

        op_layout.addWidget(btn_confirm)
        op_layout.addWidget(btn_discard)
        op_widget.setLayout(op_layout)
        self._ask_pending_table.setCellWidget(row, 5, op_widget)

    def _ask_append_chat_message(self, role: str, content: str) -> None:
        """向对话历史区追加一条消息。"""
        if self._ask_chat_display is None:
            return
        label = "你" if role == "user" else "AI"
        color_token = theme_manager.token("color_primary") if role == "ai" else theme_manager.token("color_text_primary")
        self._ask_chat_display.append(
            f'<p style="margin:4px 0;"><b style="color:{color_token};">{label}：</b>{content}</p>'
        )

    def _estimate_tokens(self, text: str) -> int:
        """粗略估算文本的 Token 数量（中文字符 ≈2 token，英文单词 ≈1 token）。"""
        cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        en_chars = len(text) - cn_chars
        return int(cn_chars * 2 + en_chars * 0.25)

    def _ask_update_token_display(self) -> None:
        """更新 Token 圆圈和标签：估算当前对话总 Token 并显示使用率。"""
        total_text = "".join(m.get("content", "") for m in self._ask_messages)
        estimated = self._estimate_tokens(total_text)
        # 模型上下文上限（常见值）
        context_limit = 8192
        model = str(self.state.get("paperhub_model", "qwen3-max"))
        if "128" in model:
            context_limit = 128000
        elif "32" in model:
            context_limit = 32000
        elif "max" in model or "pro" in model:
            context_limit = 32000

        ratio = estimated / context_limit if context_limit > 0 else 0.0

        if self._ask_token_circle is not None:
            self._ask_token_circle.set_ratio(ratio)
        if self._ask_token_label is not None:
            msg_count = len(self._ask_messages)
            self._ask_token_label.setText(
                f"消息 {msg_count} 条 · ~{estimated} / {context_limit} Token"
            )

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
            self._set_language_tooltip(item, lang)
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

    def _set_language_tooltip(self, item: QListWidgetItem, lang: Dict) -> None:
        """Set tooltip on a language list item from the notes field.
        If notes is empty or missing, no tooltip is shown."""
        notes = lang.get("notes", "").strip()
        if notes:
            item.setToolTip(notes)
        else:
            item.setToolTip("")

    def _refresh_list_item_for_language(self, lang_id: str) -> None:
        assert self.language_list is not None
        for i in range(self.language_list.count()):
            item = self.language_list.item(i)
            if item and item.data(Qt.UserRole) == lang_id:
                lang = self._language_by_id(lang_id)
                if lang:
                    item.setText(self._language_row_text(lang))
                    self._set_language_tooltip(item, lang)
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
        dlg = PaperHubSettingsDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self._paperhub_settings = load_paperhub_settings()
            self.statusBar().showMessage("PaperHub 设置已保存", 4000)

    def _open_appearance_settings(self) -> None:
        """打开外观与主题设置对话框。"""
        dlg = AppearanceDialog(self)
        dlg.exec_()

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
        self._set_language_tooltip(item, language)
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
            # Refresh tooltip for current language item
            cur_row = self.language_list.currentRow()
            if cur_row >= 0:
                item = self.language_list.item(cur_row)
                if item:
                    self._set_language_tooltip(item, lang)
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
                self._set_language_tooltip(item, lang)

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

        # ── 翻译开始：清空所有输出区域（防止残留上次内容）────────────
        if self.target_output is not None:
            self.target_output.clear()
        if self.tts_output is not None:
            self.tts_output.clear()
        self.clear_realtime_generation()
        self.clear_ipa_output()

        # ── 始终执行规则翻译（提供匹配统计）────────────────────────
        rule_result = translate_multiline_rule(text, lexicon, tts_map)
        self._last_rule_result = rule_result

        # ── 判断是否需要 PaperHub AI ────────────────────────────────
        self._paperhub_settings = load_paperhub_settings()
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
        # 流式输出：token 实时追加到「实时生成过程」模块，不写入自创语输出框
        if self._paperhub_settings.get("paperhub_stream", True):
            self._ph_thread.stream_chunk.connect(self._on_stream_chunk)
        self._ph_thread.start()

    def _on_stream_chunk(self, piece: str) -> None:
        """AI 流式输出块回调：追加到「实时生成过程」模块，不写入自创语输出框。"""
        self.append_realtime_generation(piece)

    # ------------------------------------------------------------------
    # 实时生成过程 / 国际音标读音 helper 方法
    # ------------------------------------------------------------------

    def append_realtime_generation(self, text: str) -> None:
        """追加文本到「实时生成过程」模块。"""
        if self._realtime_output is None:
            return
        cursor = self._realtime_output.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText(text)
        self._realtime_output.setTextCursor(cursor)

    def clear_realtime_generation(self) -> None:
        """清空「实时生成过程」模块。"""
        if self._realtime_output is not None:
            self._realtime_output.clear()

    def update_ipa_output(self, text: str) -> None:
        """更新「国际音标读音」模块（供后续 IPA 生成逻辑调用）。"""
        if self.ipa_output is not None:
            self.ipa_output.setPlainText(text)

    def clear_ipa_output(self) -> None:
        """清空「国际音标读音」模块。"""
        if self.ipa_output is not None:
            self.ipa_output.clear()

    def _get_ipa_map(self, lang: Dict) -> Dict[str, str]:
        """
        获取当前语言的 IPA 映射表。
        优先从已缓存的 bundle 读取；若 bundle 中无 ipa_map（旧快照），
        则直接从磁盘 Mapping_Rules.csv 读取并回写到 bundle。
        """
        bundle = self._material_by_lang.get(lang.get("id", ""), {})
        ipa_map: Dict[str, str] = bundle.get("ipa_map") or {}
        if not ipa_map:
            try:
                mapping_path = self.storage.asset_path(lang, "mapping_rules")
                if mapping_path.is_file():
                    ipa_map, _ = load_ipa_mapping(mapping_path)
                    bundle["ipa_map"] = ipa_map
            except Exception:
                pass
        return {str(k): str(v) for k, v in ipa_map.items() if str(k).strip()}

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
                self._ask_add_new_words_to_lexicon(
                    confirm_result.new_words, lang,
                    unmatched_words=list(rule_result.unmatched_words),
                )
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
                self._ask_add_new_words_to_lexicon(
                    ph_result.new_words, lang,
                    unmatched_words=list(rule_result.unmatched_words),
                )

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

        # ── 国际音标读音 ──────────────────────────────────────────
        if conlang.strip():
            ipa_map = self._get_ipa_map(lang)
            if ipa_map:
                ipa_str, _missing = generate_ipa_rule(conlang, ipa_map)
                self.update_ipa_output(ipa_str)
            else:
                self.update_ipa_output("")
        else:
            self.update_ipa_output("")

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
        self._paperhub_settings = load_paperhub_settings()

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

    def _ask_add_new_words_to_lexicon(
        self,
        new_words: List[NewWord],
        lang: Dict,
        *,
        unmatched_words: Optional[List[str]] = None,
    ) -> None:
        """翻译完成后，如果有新创词汇，询问用户是否添加到词库。

        unmatched_words：规则翻译器产出的未匹配词列表（精确分词键）。
        传入后会修正 AI 新词的 chinese 字段，确保写入词库的键与下次分词完全一致。
        """
        if not new_words:
            return

        # ── 修正 chinese 键：用 unmatched_words 的精确分词结果覆盖 AI 自己的解释 ──
        # AI 返回的 nw.chinese 可能与规则分词器产出的 unmatched_words 有细微差异，
        # 以 unmatched_words 为准，确保下次翻译时词库命中。
        if unmatched_words:
            # 构建 AI 新词的 conlang 映射（用 AI 的 chinese 作临时 key 查 conlang）
            ai_map: Dict[str, NewWord] = {nw.chinese.strip(): nw for nw in new_words if nw.chinese.strip()}
            corrected: List[NewWord] = []
            for uw in unmatched_words:
                uw = uw.strip()
                if not uw:
                    continue
                if uw in ai_map:
                    # 完全匹配：直接使用
                    corrected.append(ai_map[uw])
                else:
                    # 不完全匹配：尝试包含关系（AI 词包含 unmatched_word 或反过来）
                    found = next(
                        (nw for k, nw in ai_map.items() if uw in k or k in uw),
                        None,
                    )
                    if found:
                        # 强制用精确的 unmatched_word 作为词库键
                        from dataclasses import replace as dc_replace
                        corrected.append(dc_replace(found, chinese=uw))
            # 合并：corrected 优先，其余保留原 new_words 中未被覆盖的词
            covered_conlangs = {nw.conlang for nw in corrected}
            for nw in new_words:
                if nw.conlang not in covered_conlangs:
                    corrected.append(nw)
            if corrected:
                new_words = corrected

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
            "（添加后下次翻译时词库将直接命中这些词，不再调用 AI）",
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
        self._paperhub_settings = load_paperhub_settings()

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

    # ── 批量翻译（阶段八）─────────────────────────────────────────────

    def _pick_excel(self) -> None:
        """选择 Excel 台本文件：读取 → 验证 → 显示预览和统计。"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Excel 台本", str(Path.home()),
            "Excel Files (*.xlsx *.xls);;All Files (*.*)",
        )
        if not path:
            return

        self._excel_path = path

        # 执行导入
        result = read_excel(path)
        self._excel_import_result = result

        if not result.ok:
            QMessageBox.critical(
                self, "导入失败",
                f"读取 Excel 文件失败：\n{result.error}",
            )
            if self.batch_path_display is not None:
                self.batch_path_display.setText(f"导入失败：{Path(path).name}")
            return

        # 显示文件路径
        if self.batch_path_display is not None:
            self.batch_path_display.setText(path)

        if self.batch_log is not None:
            self.batch_log.clear()
            self.batch_log.appendPlainText(f"已选择：{path}")

        # 检查必需列
        if result.missing_columns:
            missing_text = ", ".join(result.missing_columns)
            QMessageBox.warning(
                self, "缺少必需列",
                f"以下必需列在 Excel 中未找到：\n{missing_text}\n\n"
                "请确保 Excel 首行包含以下列名：\n"
                "台本ID, Character, Age, Gender, Body_Type, Emotion, Scene_Context, Text",
            )
            if self.batch_log is not None:
                self.batch_log.appendPlainText(f"⚠ 缺少列：{missing_text}")
            # 缺列仍可继续（缺失列数据为空）

        # ── 显示预览 ──────────────────────────────────────────────
        stats = result.statistics
        preview_lines: List[str] = []
        preview_lines.append(f"统计信息：")
        preview_lines.append(f"  总行数：{stats.total_rows}")
        preview_lines.append(f"  角色数量：{stats.character_count}")
        if stats.characters:
            preview_lines.append(f"  角色：{', '.join(stats.characters[:10])}"
                                + ("…" if len(stats.characters) > 10 else ""))
        preview_lines.append(f"  情绪类型：{stats.emotion_count}")
        if stats.emotion_types:
            preview_lines.append(f"  情绪：{', '.join(stats.emotion_types[:10])}"
                                + ("…" if len(stats.emotion_types) > 10 else ""))
        preview_lines.append("")
        preview_lines.append("预览（前5行）：")

        # 构建预览表格

        preview_rows = result.preview_rows
        columns = result.columns

        preview_dlg = QDialog(self)
        preview_dlg.setWindowTitle("Excel 台本预览")
        preview_dlg.setMinimumWidth(720)
        preview_dlg.setMinimumHeight(400)
        preview_layout = QVBoxLayout(preview_dlg)

        # 统计标签
        stats_text = (
            f"总行数：{stats.total_rows}　"
            f"角色数量：{stats.character_count}　"
            f"情绪类型：{stats.emotion_count}"
        )
        stats_label = QLabel(stats_text)
        stats_label.setProperty("class", "heading")

        stats_label.setObjectName("cls_heading")

        preview_layout.addWidget(stats_label)

        # 预览表格（最多5行）
        if preview_rows:
            table = QTableWidget(min(len(preview_rows), 5), len(columns))
            table.setHorizontalHeaderLabels(columns)
            table.setAlternatingRowColors(True)
            table.horizontalHeader().setStretchLastSection(True)
            table.setEditTriggers(QTableWidget.NoEditTriggers)

            for row_idx, prow in enumerate(preview_rows[:5]):
                for col_idx, col_name in enumerate(columns):
                    val = prow.data.get(col_name, "")
                    # 截断过长内容
                    display = str(val)[:60] + ("…" if len(str(val)) > 60 else "")
                    item = QTableWidgetItem(display)
                    table.setItem(row_idx, col_idx, item)

            table.resizeColumnsToContents()
            preview_layout.addWidget(table)
        else:
            preview_layout.addWidget(QLabel("（无数据行）"))

        preview_layout.addStretch(1)

        btn_close_preview = QPushButton("关闭")
        btn_close_preview.clicked.connect(preview_dlg.accept)
        preview_layout.addWidget(btn_close_preview)

        preview_dlg.exec_()

        if self.batch_log is not None:
            self.batch_log.appendPlainText(stats_text)
            self.batch_log.appendPlainText(f"共 {len(result.rows)} 行数据待翻译。")

        # 刷新资料状态（可能已更新词库）
        self._refresh_asset_status()

    def _on_batch_start(self) -> None:
        """开始批量翻译：弹出设置对话框 → 启动翻译线程。"""
        if not self._excel_import_result or not self._excel_import_result.ok:
            QMessageBox.warning(
                self, "未导入 Excel",
                "请先点击「选择 Excel」导入台本文件。",
            )
            return

        if self._batch_worker is not None and self._batch_worker.isRunning():
            QMessageBox.warning(
                self, "翻译进行中",
                "批量翻译正在进行，请等待完成或取消后再试。",
            )
            return

        lang = self.get_current_language()
        if lang is None:
            QMessageBox.warning(self, "未选择语言", "请先选择一个语言。")
            return

        # 弹出批量翻译设置对话框
        dlg = BatchTranslateDialog(
            current_settings=self._batch_translate_settings,
            paperhub_settings=self._paperhub_settings,
            parent=self,
        )
        if dlg.exec_() != QDialog.Accepted:
            return

        settings = dlg.get_settings()
        self._batch_translate_settings = settings

        # 构建翻译 bundle
        self._ensure_material_bundle(lang)
        bundle = dict(self.get_language_material_bundle(lang.get("id", "")))

        # 添加文件路径到 bundle（供自动写入词库使用）
        bundle["master_library_path"] = str(self.storage.asset_path(lang, "master_library"))
        bundle["mapping_rules_path"] = str(self.storage.asset_path(lang, "mapping_rules"))

        # 创建翻译线程
        rows = self._excel_import_result.rows
        self._batch_worker = BatchTranslateWorker(
            rows=rows,
            settings=settings,
            bundle=bundle,
            paperhub_settings=self._paperhub_settings,
            parent=self,
        )
        self._batch_worker.progress.connect(self._on_batch_progress)
        self._batch_worker.finished.connect(self._on_batch_finished)
        self._batch_worker.log_message.connect(self._on_batch_log)

        # UI 进入翻译状态
        if self.batch_progress is not None:
            self.batch_progress.setRange(0, len(rows))
            self.batch_progress.setValue(0)
            self.batch_progress.setFormat("翻译中… %p%")

        # 按钮状态：禁用开始，显示暂停/取消
        if self._btn_batch_start is not None:
            self._btn_batch_start.setEnabled(False)
        if self._btn_batch_pause is not None:
            self._btn_batch_pause.setVisible(True)
            self._btn_batch_pause.setText("暂停")
        if self._btn_batch_cancel is not None:
            self._btn_batch_cancel.setVisible(True)

        if self.batch_log is not None:
            mode_names = {"rule": "规则翻译", "hybrid": "混合翻译", "ai": "AI翻译"}
            self.batch_log.appendPlainText(
                f"开始批量翻译（{mode_names.get(settings.mode, settings.mode)}）"
            )
            self.batch_log.appendPlainText(f"模型：{settings.model}  并发：{settings.concurrency}  间隔：{settings.request_interval}s")

        self._batch_results = []
        self.statusBar().showMessage("批量翻译进行中…")
        self._batch_worker.start()

    def _on_batch_progress(self, row_index: int, total: int, result: BatchTranslateResult) -> None:
        """每行翻译完成的回调。"""
        if self.batch_progress is not None:
            self.batch_progress.setValue(row_index + 1)

        if self.batch_log is not None:
            row_id = result.row_id or str(result.row_index)
            if result.error:
                self.batch_log.appendPlainText(
                    f"  [{row_id}] ❌ {result.chinese_text[:30]}… → 错误：{result.error[:60]}"
                )
            elif result.mode_used == "skip":
                self.batch_log.appendPlainText(f"  [{row_id}] ⊘ 空行跳过")
            else:
                unmatched_tag = ""
                if result.unmatched_words:
                    unmatched_tag = f" （未匹配{len(result.unmatched_words)}词）"
                self.batch_log.appendPlainText(
                    f"  [{row_id}] ✓ {result.chinese_text[:30]}… → {result.conlang[:30]}…{unmatched_tag}"
                )

    def _on_batch_finished(
        self,
        results: List[BatchTranslateResult],
        unmatched_entries: List[UnmatchedWordEntry],
        error_msg: str,
    ) -> None:
        """批量翻译全部完成的回调。"""
        self._batch_results = results

        # ── 恢复按钮状态 ────────────────────────────────────────
        if self._btn_batch_start is not None:
            self._btn_batch_start.setEnabled(True)
        if self._btn_batch_pause is not None:
            self._btn_batch_pause.setVisible(False)
        if self._btn_batch_cancel is not None:
            self._btn_batch_cancel.setVisible(False)

        if self.batch_log is not None:
            if error_msg:
                self.batch_log.appendPlainText(f"⚠ 批量翻译中断：{error_msg}")
            else:
                success_count = sum(1 for r in results if r.conlang and not r.error)
                error_count = sum(1 for r in results if r.error)
                skip_count = sum(1 for r in results if r.mode_used == "skip")
                total_count = len(results)
                self.batch_log.appendPlainText(
                    f"批量翻译完成！总计 {total_count} 行 "
                    f"（成功 {success_count}，跳过 {skip_count}，错误 {error_count}）"
                )

            if unmatched_entries:
                self.batch_log.appendPlainText(f"未匹配词汇：{len(unmatched_entries)} 个")

        if self.batch_progress is not None:
            self.batch_progress.setFormat("完成 ✓ %p%")

        self.statusBar().showMessage("批量翻译完成", 5000)

        # ── 如果有未匹配词汇且有 AI 自动添加未成功，弹出处理对话框 ────
        filled_unmatched = [e for e in unmatched_entries if e.conlang]
        unfilled_unmatched = [e for e in unmatched_entries if not e.conlang]

        if unfilled_unmatched and self._batch_translate_settings:
            bundle = dict(self.get_language_material_bundle())
            dlg = UnmatchedWordsDialog(
                unmatched_words=[e.chinese for e in unfilled_unmatched],
                bundle=bundle,
                paperhub_settings=self._paperhub_settings,
                parent=self,
            )
            if dlg.exec_() == QDialog.Accepted:
                entries = dlg.get_entries()
                filled = [e for e in entries if e.conlang]
                if filled:
                    lang = self.get_current_language()
                    if lang:
                        self._write_unmatched_entries_to_lexicon(filled, lang)

        # ── 导出未匹配词汇报告（如果设置要求）─────────────────────────
        if self._batch_translate_settings and self._batch_translate_settings.export_unmatched_report:
            if unmatched_entries:
                if self._excel_path:
                    report_path = Path(self._excel_path).parent / (
                        Path(self._excel_path).stem + "_unmatched_report.csv"
                    )
                else:
                    report_path = Path.home() / "unmatched_report.csv"
                report_ok = export_unmatched_report(unmatched_entries, str(report_path))
                if report_ok and self.batch_log is not None:
                    self.batch_log.appendPlainText(f"未匹配词汇报告已导出：{report_path}")

        # ── 自动弹出「另存为」对话框（阶段十）───────────────────────
        if results and not error_msg:
            self._do_auto_export(results)

        # 刷新资料状态（可能已更新词库）
        self._refresh_asset_status()
        self._refresh_materials()

    def _do_auto_export(self, results: List[BatchTranslateResult]) -> None:
        """自动弹出另存为并执行导出（阶段十）。"""
        if self._excel_import_result is None or not self._excel_import_result.ok:
            return

        # ── 默认文件名：原文件名_TTS_Ready_时间戳.xlsx ────────────
        ts_filename = generate_timestamp_filename(self._excel_path)
        if self._excel_path:
            default_dir = str(Path(self._excel_path).parent)
        else:
            default_dir = str(Path.home() / "Documents")
        default_save = str(Path(default_dir) / ts_filename)

        output_path, _ = QFileDialog.getSaveFileName(
            self, "导出翻译结果",
            default_save,
            "Excel Files (*.xlsx);;All Files (*)",
        )
        if not output_path:
            return

        stats = export_results_to_excel(
            results=results,
            original_rows=self._excel_import_result.rows,
            output_path=output_path,
        )

        if not stats.get("success"):
            QMessageBox.critical(
                self, "导出失败",
                "导出 Excel 文件失败，请检查文件路径和 pandas / openpyxl 是否已安装。",
            )
            return

        # ── 同步追加到 Translation_History.json ────────────────────
        self._append_results_to_history(results)

        # ── 汇总新创词汇 ──────────────────────────────────────────
        all_new_words = []
        for r in results:
            all_new_words.extend(r.new_words)

        # ── 弹出导出完成对话框 ────────────────────────────────────
        dlg = ExportResultDialog(stats, output_path, all_new_words, parent=self)
        dlg.exec_()

        # ── 如果用户选择了「全部添加到词库」────────────────────────
        # （NewWordsReportDialog 通过 get_added_to_lexicon 返回标记）
        # ExportResultDialog 内嵌了 NewWordsReportDialog，
        # 我们需要在 ExportResultDialog 中追踪此状态
        # 已在 NewWordsReportDialog._add_to_lexicon 中标记，
        # ExportResultDialog 暂时无回传机制，词库更新由 Worker 的
        # auto_add_new_words 处理，或由用户手动触发

        # ── 日志反馈 ──────────────────────────────────────────────
        if self.batch_log is not None:
            self.batch_log.appendPlainText(f"导出成功：{output_path}")

    def _append_results_to_history(
        self,
        results: List[BatchTranslateResult],
    ) -> None:
        """将所有翻译结果追加到 Translation_History.json。"""
        lang = self.get_current_language()
        if lang is None:
            return

        # 获取语言配置
        lang_id = lang.get("id", "")
        bundle = self._material_by_lang.get(lang_id, {})
        lang_name = lang.get("name", lang_id)

        # 找到 history 文件路径
        history_path = bundle.get("translation_history_path")
        if not history_path:
            return

        history_file = Path(history_path)
        for r in results:
            if not r.conlang:
                continue  # 跳过空行/跳过行

            append_translation_record(
                history_file,
                source=r.chinese_text,
                conlang=r.conlang,
                phonetic=r.tts,
                unmatched_words=r.unmatched_words,
                source_language="中文",
                target_language=lang_name,
                translation_mode=r.mode_used,
                emotion_label=r.emotion.lower() if r.emotion else "neutral",
                emotion_intensity=0.5,
                tts_pitch_hint="normal",
                tts_rate_hint="normal",
            )

    def _on_batch_log(self, msg: str) -> None:
        """接收 Worker 的实时日志消息。"""
        if self.batch_log is not None:
            self.batch_log.appendPlainText(msg)

    def _on_batch_pause_resume(self) -> None:
        """暂停/继续批量翻译。"""
        if self._batch_worker is None or not self._batch_worker.isRunning():
            return

        if self._batch_worker.is_paused:
            self._batch_worker.resume()
            if self._btn_batch_pause is not None:
                self._btn_batch_pause.setText("暂停")
            if self.batch_log is not None:
                self.batch_log.appendPlainText("▶ 继续翻译…")
            self.statusBar().showMessage("批量翻译进行中…")
        else:
            self._batch_worker.pause()
            if self._btn_batch_pause is not None:
                self._btn_batch_pause.setText("继续")
            if self.batch_log is not None:
                self.batch_log.appendPlainText("⏸ 翻译已暂停")
            self.statusBar().showMessage("批量翻译已暂停")

    def _on_batch_cancel(self) -> None:
        """取消批量翻译。"""
        if self._batch_worker is None or not self._batch_worker.isRunning():
            return

        confirm = QMessageBox.question(
            self, "确认取消",
            "确定要取消当前批量翻译吗？已翻译的行将保留。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        self._batch_worker.cancel()
        if self.batch_log is not None:
            self.batch_log.appendPlainText("⚠ 正在取消…")

    def _refresh_materials(self) -> None:
        """重新从磁盘加载资料 bundle（批量翻译可能已更新词库）。"""
        lang = self.get_current_language()
        if lang is None:
            return
        bid = lang.get("id", "")
        if bid in self._material_by_lang:
            rep = refresh_materials_from_disk(self.storage, lang)
            self._material_by_lang[bid] = rep.bundle

    def _on_batch_export(self) -> None:
        """手动重新导出翻译结果为 Excel 文件（阶段十增强版）。"""
        if not self._batch_results:
            QMessageBox.warning(
                self, "无翻译结果",
                "尚未完成批量翻译，请先执行翻译后再导出。",
            )
            return

        if self._excel_import_result is None or not self._excel_import_result.ok:
            QMessageBox.warning(self, "导出失败", "原始 Excel 数据不可用。")
            return

        # 默认导出路径：使用时间戳命名
        if self._excel_path:
            default_dir = str(Path(self._excel_path).parent)
            default_name = generate_timestamp_filename(self._excel_path)
        else:
            default_dir = str(Path.home() / "Documents")
            default_name = generate_timestamp_filename("")
        default_save = str(Path(default_dir) / default_name)

        output_path, _ = QFileDialog.getSaveFileName(
            self, "导出翻译结果",
            default_save,
            "Excel Files (*.xlsx);;All Files (*)",
        )
        if not output_path:
            return

        stats = export_results_to_excel(
            results=self._batch_results,
            original_rows=self._excel_import_result.rows,
            output_path=output_path,
        )

        if not stats.get("success"):
            QMessageBox.critical(
                self, "导出失败",
                "导出 Excel 文件失败，请检查文件路径和 pandas / openpyxl 是否已安装。",
            )
            return

        # 同步到翻译历史
        self._append_results_to_history(self._batch_results)

        # 收集所有新词汇
        all_new_words: List = []
        for r in self._batch_results:
            if r.new_words:
                all_new_words.extend(r.new_words)

        # 展示导出完成对话框
        from app.export_result_dialog import ExportResultDialog
        dlg = ExportResultDialog(stats, output_path, all_new_words, parent=self)
        dlg.exec_()

        if self.batch_log is not None:
            self.batch_log.appendPlainText("导出成功：" + output_path)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于 Nikki Conlang Forge",
            "<b>Nikki Conlang Forge</b><br>"
            "无限暖暖自创语翻译器<br><br>"
            "阶段十：导出增强与历史同步已完成。<br>"
            "支持规则翻译 / 混合翻译 / AI翻译三种模式<br>"
            " + SSML 语音标签（基于 Emotion / Body_Type / Age）<br>"
            " + 暂停 / 继续 / 取消批量翻译 + AI限流重试<br>"
            " + Excel 导入（预览+统计+验证）<br>"
            " + 时间戳命名导出 + 统计对话框 + 新创词汇报告<br>"
            " + 翻译结果自动同步到 Translation_History.json<br>"
            " + AI生成追踪（AI_Generated / AI_Model列）。",
        )