from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPen, QBrush
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QApplication as QApp,
)

from app.app_paths import get_icon_path
from app.models.pending_words import PendingWordStore
from app.paperhub_client import NewWord
from app.paperhub_settings import load_ask_templates, load_paperhub_settings, save_ask_templates
from app.ui_theme import theme_manager


# ---------------------------------------------------------------------------
# ASK 异步对话线程
# ---------------------------------------------------------------------------

class _AskChatThread(QThread):
    """后台线程执行 ASK 多轮对话 AI 调用。"""

    finished = pyqtSignal(str, str)     # (full_text, error_message)
    stream_chunk = pyqtSignal(str)      # 流式输出块

    def __init__(
        self,
        settings: Dict[str, Any],
        system_prompt: str,
        messages: List[Dict[str, str]],
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._system_prompt = system_prompt
        self._messages = messages

    def run(self) -> None:
        from app.paperhub_client import _make_error_hint

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
                # 墙钟超时守卫：SDK timeout 只管单次读写，流式逐 chunk 接收可能绕过
                deadline = time.monotonic() + timeout
                for chunk in client.chat.completions.create(**create_kwargs):
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"流式响应超时（墙钟 {timeout}s）")
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


# ---------------------------------------------------------------------------
# Token 圆环控件
# ---------------------------------------------------------------------------

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
        from PyQt5.QtGui import QColor, QPainter, QPen, QBrush
        from app.ui_theme import theme_manager

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2
        cy = h / 2
        pen_width = 6
        radius = min(w, h) / 2 - pen_width / 2

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
            if ratio < 0.5:
                arc_color = QColor("#4CAF50")
            elif ratio < 0.8:
                arc_color = QColor(theme_manager.token("color_primary") or "#2196F3")
            else:
                arc_color = QColor("#F44336")

            painter.setPen(QPen(arc_color, pen_width, Qt.SolidLine, Qt.RoundCap))
            painter.setBrush(QBrush(QColor(0, 0, 0, 0)))
            start_angle = 90 * 16
            span_angle = -int(ratio * 360 * 16)
            painter.drawArc(
                int(cx - radius), int(cy - radius),
                int(2 * radius), int(2 * radius),
                start_angle, span_angle,
            )

        # 中心文字（百分比）
        pct_text = f"{int(self._ratio * 100)}%"
        font = QFont()
        font.setPixelSize(max(10, int(radius * 0.6)))
        font.setBold(True)
        painter.setFont(font)
        text_color = QColor(theme_manager.token("color_text_primary") or "#EEEEEE")
        painter.setPen(QPen(text_color))
        painter.drawText(self.rect(), Qt.AlignCenter, pct_text)

        painter.end()


# ---------------------------------------------------------------------------
# AskController
# ---------------------------------------------------------------------------

class AskController(QObject):
    """语言大师对话页签的所有状态、UI、交互逻辑。

    通过 self._mw 引用 MainWindow，跨类访问主窗口的资源
    （当前语言、bundle、词库写盘、statusBar 等）。
    """

    def __init__(self, mw) -> None:
        super().__init__(parent=mw)
        self._mw = mw

        # ── UI 引用 ──────────────────────────────────────────────────
        self._ask_chat_display: Optional[QTextEdit] = None
        self._ask_input: Optional[QPlainTextEdit] = None
        self._ask_send_btn: Optional[QPushButton] = None
        self._ask_clear_btn: Optional[QPushButton] = None
        self._ask_token_circle: Optional[QWidget] = None
        self._ask_pending_panel: Optional[QWidget] = None
        self._ask_pending_table: Optional[QTableWidget] = None
        self._ask_pending_toggle: Optional[QPushButton] = None
        self._ask_batch_confirm_btn: Optional[QPushButton] = None
        self._ask_batch_discard_btn: Optional[QPushButton] = None
        self._ask_confirm_selected_btn: Optional[QPushButton] = None
        self._ask_discard_selected_btn: Optional[QPushButton] = None

        # ── 模板 ─────────────────────────────────────────────────────
        self._ask_templates: List[Dict[str, str]] = load_ask_templates()
        self._ask_template_btns: List[QPushButton] = []
        self._ask_template_row: Optional[QHBoxLayout] = None

        # ── 会话状态 ─────────────────────────────────────────────────
        self._ask_messages: List[Dict[str, str]] = []
        self._ask_chat_thread: Optional[_AskChatThread] = None
        self._ask_ai_pending: str = ""
        self._ask_ai_just_started: bool = False

        # ── 检索热词集合 ─────────────────────────────────────────────
        self._ask_hot_words: List[str] = []
        self._ask_hot_words_max: int = 200

        # ── 候选词 store（source of truth） ──────────────────────────
        self._ask_pending_store = PendingWordStore()

    # ── UI 构建 ───────────────────────────────────────────────────────────

    def build_page(self) -> QWidget:
        """构建 ASK 页签（AI 对话模式）— 上中下三区可拉伸布局。"""
        page = QWidget()
        page.setObjectName("cls_ask_page")
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(24, 24, 24, 24)
        page_layout.setSpacing(24)

        # ── 垂直分割器：上(对话) → 中(待审核) → 下(提问) ────────
        v_splitter = QSplitter(Qt.Vertical)
        v_splitter.setObjectName("cls_ask_v_splitter")

        # ── 上区：对话历史 ────────────────────────────────────────
        chat_wrap = QWidget()
        chat_wrap.setObjectName("cls_ask_chat_wrap")
        chat_layout = QVBoxLayout(chat_wrap)
        chat_layout.setContentsMargins(0, 0, 0, 4)
        chat_layout.setSpacing(16)

        chat_hdr = QHBoxLayout()
        _title = QLabel("对话历史")
        _title.setProperty("class", "section-title")
        _title.setObjectName("cls_section_title")
        chat_hdr.addWidget(_title)
        chat_hdr.addStretch(1)
        self._ask_token_circle = _TokenCircleWidget()
        self._ask_token_circle.setFixedSize(38, 38)
        self._ask_token_circle.setObjectName("cls_ask_token_circle")
        self._ask_token_circle.setToolTip("— / —")
        chat_hdr.addWidget(self._ask_token_circle, 0, Qt.AlignVCenter)
        self._ask_clear_btn = QPushButton("清空")
        self._ask_clear_btn.setProperty("class", "bold-small")
        self._ask_clear_btn.setObjectName("cls_bold_small")
        self._ask_clear_btn.setFixedHeight(38)
        self._ask_clear_btn.clicked.connect(self._ask_clear_conversation)
        chat_hdr.addWidget(self._ask_clear_btn, 0, Qt.AlignVCenter)
        chat_layout.addLayout(chat_hdr)

        self._ask_chat_display = QTextEdit()
        self._ask_chat_display.setReadOnly(True)
        self._ask_chat_display.setObjectName("cls_ask_chat_display")
        self._ask_chat_display.setProperty("class", "chat-display")
        self._ask_chat_display.setPlaceholderText(
            "在这里与 AI 进行对话，探讨翻译方案、词库创作…"
        )
        chat_layout.addWidget(self._ask_chat_display, 1)

        v_splitter.addWidget(chat_wrap)

        # ── 中区：待审核候选词 ────────────────────────────────────
        pending_wrap = QWidget()
        pending_wrap.setObjectName("cls_ask_pending_wrap")
        pending_layout = QVBoxLayout(pending_wrap)
        pending_layout.setContentsMargins(0, 8, 0, 8)
        pending_layout.setSpacing(16)

        pending_hdr = QHBoxLayout()
        _title = QLabel("待审核候选词")
        _title.setProperty("class", "section-title")
        _title.setObjectName("cls_section_title")
        pending_hdr.addWidget(_title)
        pending_hdr.addStretch(1)

        self._ask_pending_toggle = QPushButton("收起")
        self._ask_pending_toggle.setProperty("class", "bold-small")
        self._ask_pending_toggle.setObjectName("cls_ask_pending_toggle_btn")
        self._ask_pending_toggle.clicked.connect(self._toggle_ask_pending)
        pending_hdr.addWidget(self._ask_pending_toggle)

        self._ask_batch_confirm_btn = QPushButton("全部确认")
        self._ask_batch_confirm_btn.setProperty("class", "bold-primary-sm")
        self._ask_batch_confirm_btn.setObjectName("cls_bold_primary_sm")
        self._ask_batch_confirm_btn.clicked.connect(self._ask_batch_confirm_pending)
        self._ask_batch_confirm_btn.setVisible(False)
        pending_hdr.addWidget(self._ask_batch_confirm_btn)

        self._ask_batch_discard_btn = QPushButton("全部丢弃")
        self._ask_batch_discard_btn.setProperty("class", "bold-small")
        self._ask_batch_discard_btn.setObjectName("cls_bold_small")
        self._ask_batch_discard_btn.clicked.connect(self._ask_batch_discard_pending)
        self._ask_batch_discard_btn.setVisible(False)
        pending_hdr.addWidget(self._ask_batch_discard_btn)

        self._ask_confirm_selected_btn = QPushButton("确认选中")
        self._ask_confirm_selected_btn.setProperty("class", "bold-primary-sm")
        self._ask_confirm_selected_btn.setObjectName("cls_bold_primary_sm")
        self._ask_confirm_selected_btn.clicked.connect(self._ask_confirm_selected_pending)
        self._ask_confirm_selected_btn.setVisible(False)
        pending_hdr.addWidget(self._ask_confirm_selected_btn)

        self._ask_discard_selected_btn = QPushButton("丢弃选中")
        self._ask_discard_selected_btn.setProperty("class", "bold-small")
        self._ask_discard_selected_btn.setObjectName("cls_bold_small")
        self._ask_discard_selected_btn.clicked.connect(self._ask_discard_selected_pending)
        self._ask_discard_selected_btn.setVisible(False)
        pending_hdr.addWidget(self._ask_discard_selected_btn)

        pending_layout.addLayout(pending_hdr)

        self._ask_pending_table = QTableWidget(0, 6)
        self._ask_pending_table.setObjectName("cls_ask_pending_table")
        self._ask_pending_table.setHorizontalHeaderLabels(
            ["自创语", "IPA", "TTS", "含义", "风格标签", "操作"]
        )
        self._ask_pending_table.horizontalHeader().setStretchLastSection(False)
        for i in range(5):
            self._ask_pending_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.Stretch)
        self._ask_pending_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self._ask_pending_table.setColumnWidth(5, 80)
        self._ask_pending_table.setSelectionBehavior(QTableWidget.SelectItems)
        self._ask_pending_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self._ask_pending_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._ask_pending_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._ask_pending_table.customContextMenuRequested.connect(self._ask_on_table_context_menu)
        pending_layout.addWidget(self._ask_pending_table, 1)

        self._ask_pending_panel = pending_wrap
        v_splitter.addWidget(pending_wrap)

        # ── 下区：提问输入区 ──────────────────────────────────────
        input_wrap = QWidget()
        input_wrap.setObjectName("cls_ask_input_wrap")
        input_layout = QVBoxLayout(input_wrap)
        input_layout.setContentsMargins(0, 8, 0, 0)
        input_layout.setSpacing(16)

        # 快捷提问模板按钮行（动态构建）
        template_row = QHBoxLayout()
        template_row.setSpacing(8)
        self._ask_template_row = template_row
        input_layout.addLayout(template_row)
        self._rebuild_template_buttons()

        # 输入框 + 发送按钮
        input_row = QHBoxLayout()
        input_row.setSpacing(16)

        self._ask_input = QPlainTextEdit()
        self._ask_input.setPlaceholderText("输入你的问题，按发送或 Ctrl+Enter 提交…")
        self._ask_input.setMinimumHeight(60)
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

    # ── 对话交互 ──────────────────────────────────────────────────────────

    def _ask_clear_conversation(self) -> None:
        """清空 ASK 对话历史和 Token 计数。"""
        self._ask_messages.clear()
        self._ask_hot_words.clear()
        if self._ask_chat_display is not None:
            self._ask_chat_display.clear()
        self._ask_update_token_display()

    def _ask_send_message(self) -> None:
        """发送用户提问，触发 AI 多轮对话。"""
        if self._ask_input is None or self._ask_send_btn is None:
            return
        if self._ask_chat_thread is not None:
            try:
                if self._ask_chat_thread.isRunning():
                    return
            except RuntimeError:
                self._ask_chat_thread = None

        user_text = self._ask_input.toPlainText().strip()
        if not user_text:
            return

        self._ask_append_chat_message("user", user_text)
        self._ask_messages.append({"role": "user", "content": user_text})
        self._ask_input.clear()
        self._ask_update_token_display()

        # 重新加载 PaperHub 设置（用户可能刚改过配置）
        self._mw._paperhub_settings = load_paperhub_settings()
        settings = self._mw._paperhub_settings

        if not settings.get("paperhub_enabled", False):
            self._ask_append_chat_message("system",
                "⚠ PaperHub AI 未启用，请在「设置 → PaperHub 设置」中开启。")
            return

        api_key = str(settings.get("paperhub_api_key") or "").strip()
        if not api_key:
            self._ask_append_chat_message("system",
                "⚠ 未填写 PaperHub API Key，请在「设置 → PaperHub 设置」中配置。")
            return

        lang = self._mw.get_current_language()
        if lang is None:
            self._ask_append_chat_message("system",
                "⚠ 请先在左侧面板选择一种语言。")
            return
        self._mw._ensure_material_bundle(lang)
        bundle = self._mw._material_by_lang.get(lang.get("id", ""), {})
        self._mw._ph_lang = lang
        self._mw._ph_bundle = bundle
        try:
            self._ask_accumulate_hot_words(user_text, bundle)
        except Exception:
            pass
        system_prompt = self._build_ask_system_prompt(bundle, current_input=user_text)

        self._ask_send_btn.setEnabled(False)
        self._ask_send_btn.setText("思考中…")
        self._ask_ai_pending = ""
        self._ask_ai_just_started = True

        self._ask_chat_thread = _AskChatThread(
            settings=settings,
            system_prompt=system_prompt,
            messages=self._ask_messages,
        )
        self._ask_chat_thread.stream_chunk.connect(self._ask_on_stream_chunk)
        self._ask_chat_thread.finished.connect(self._ask_on_chat_finished)
        self._ask_chat_thread.finished.connect(self._ask_chat_thread.deleteLater)
        self._ask_chat_thread.start()

    def _ask_on_stream_chunk(self, piece: str) -> None:
        """流式接收 AI 响应块，实时追加到对话区。"""
        if self._ask_chat_display is None:
            return
        self._ask_ai_pending += piece

        if self._ask_ai_just_started:
            self._ask_chat_display.append(
                f'<p style="margin:4px 0;"><b style="color:#6B6880;">DUD：</b>'
            )
            self._ask_ai_just_started = False

        cursor = self._ask_chat_display.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText(piece)
        self._ask_chat_display.setTextCursor(cursor)
        self._ask_chat_display.ensureCursorVisible()

    def _ask_on_chat_finished(self, full_text: str, error: str) -> None:
        """AI 对话完成：追加完整 AI 消息到对话历史。"""
        if self._ask_send_btn is not None:
            self._ask_send_btn.setEnabled(True)
            self._ask_send_btn.setText("发送")

        self._ask_chat_thread = None

        if error:
            self._ask_append_chat_message("system", f"⚠ {error}")
            return

        ai_text = self._ask_ai_pending if self._ask_ai_pending else full_text

        if not ai_text.strip():
            self._ask_append_chat_message("system", "AI 返回了空内容。")
            self._ask_ai_pending = ""
            return

        self._ask_messages.append({"role": "assistant", "content": ai_text})
        self._ask_update_token_display()

        if not self._ask_ai_pending:
            self._ask_append_chat_message("ai", ai_text)

        self._ask_parse_ai_response(ai_text)

        if self._mw._ph_bundle:
            try:
                self._ask_accumulate_hot_words(ai_text, self._mw._ph_bundle)
            except Exception:
                pass

        self._ask_ai_pending = ""

    def _ask_accumulate_hot_words(self, text: str, bundle: Dict[str, Any]) -> None:
        """对 text 与当前 bundle 词库做最长匹配，命中的中文词追加到会话热词集合。"""
        if not text:
            return
        lexicon = bundle.get("lexicon") or {}
        if not isinstance(lexicon, dict) or not lexicon:
            return
        try:
            from app.lexicon_segment import segment_with_lexicon
        except ImportError:
            return
        segs = segment_with_lexicon(text, {str(k): str(v) for k, v in lexicon.items() if str(k).strip()})
        existing = set(self._ask_hot_words)
        for kind, s in segs:
            if kind == "lex" and s and s not in existing:
                self._ask_hot_words.append(s)
                existing.add(s)
        if len(self._ask_hot_words) > self._ask_hot_words_max:
            drop = len(self._ask_hot_words) - self._ask_hot_words_max
            del self._ask_hot_words[:drop]

    def _build_ask_system_prompt(
        self, bundle: Dict[str, Any], current_input: Optional[str] = None
    ) -> str:
        """构建 ASK 对话模式的系统提示词（三层词库注入）。"""
        from app.paperhub_client import _whitepaper_full, _vocabulary_list

        lang_name = ""
        lang = self._mw._ph_lang
        if lang and isinstance(lang, dict):
            lang_name = lang.get("name", "")

        settings = self._mw._paperhub_settings or {}
        retrieval_enabled = bool(settings.get("prompt_retrieval_enabled", True))
        core_quota = max(0, int(settings.get("prompt_core_quota", 200)))
        hit_quota = max(0, int(settings.get("prompt_hit_quota", 500)))
        char_budget = max(500, int(settings.get("prompt_char_budget", 8000)))

        wp = _whitepaper_full(bundle)
        vocab = _vocabulary_list(
            bundle,
            input_text=current_input,
            extra_keys=list(self._ask_hot_words),
            retrieval_enabled=retrieval_enabled,
            core_quota=core_quota,
            hit_quota=hit_quota,
            char_budget=char_budget,
            max_items=120,
        )

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
        """解析 AI 响应中的【新词】行，加入候选词 store 并重渲染表格。"""
        pattern = r"【新词】(.+?)\|(.+?)\|(.+?)\|(.+?)\|(.+)"
        matches = re.findall(pattern, ai_text)
        if not matches:
            return

        for m in matches:
            conlang, ipa, tts, meaning, tags = m
            self._ask_pending_store.add_from_ai_match(
                conlang, ipa, tts, meaning, tags
            )
        self._ask_render_pending_table()

    def _ask_input_key_event(self, event) -> None:
        """拦截 Ctrl+Enter 发送消息，其余按键正常传递。"""
        from PyQt5.QtCore import Qt as QtConst
        if event.key() in (QtConst.Key_Return, QtConst.Key_Enter) and (
            event.modifiers() & QtConst.ControlModifier
        ):
            self._ask_send_message()
        else:
            QPlainTextEdit.keyPressEvent(self._ask_input, event)

    # ── 模板管理 ──────────────────────────────────────────────────────────

    def _rebuild_template_buttons(self) -> None:
        """根据 self._ask_templates 重新构建快捷提问按钮行。"""
        if self._ask_template_row is None:
            return
        self._ask_template_btns.clear()
        while self._ask_template_row.count():
            item = self._ask_template_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        label = QLabel("快捷提问：")
        label.setProperty("class", "section-title")
        label.setObjectName("cls_section_title")
        label.setAlignment(Qt.AlignVCenter)
        label.setFixedHeight(34)
        label.setStyleSheet("padding-top:0;")
        self._ask_template_row.addWidget(label, 0, Qt.AlignVCenter)

        for tpl in self._ask_templates:
            btn = QPushButton(tpl["name"])
            btn.setProperty("class", "pill")
            btn.setObjectName("cls_pill")
            btn.setToolTip(tpl["prompt"])
            btn.clicked.connect(self._ask_on_template_clicked)
            self._ask_template_btns.append(btn)
            self._ask_template_row.addWidget(btn, 0, Qt.AlignVCenter)

        manage_btn = QPushButton("管理模板…")
        manage_btn.setProperty("class", "pill")
        manage_btn.setObjectName("cls_pill")
        manage_btn.clicked.connect(self._ask_manage_templates)
        self._ask_template_btns.append(manage_btn)
        self._ask_template_row.addWidget(manage_btn, 0, Qt.AlignVCenter)

        self._ask_template_row.addStretch(1)

    def _ask_on_template_clicked(self) -> None:
        """快捷提问模板按钮点击 — 将模板 prompt 文本填入输入框。"""
        if self._ask_input is None:
            return
        sender = self.sender()
        if sender and isinstance(sender, QPushButton):
            name = sender.text()
            for tpl in self._ask_templates:
                if tpl["name"] == name:
                    self._ask_input.setPlainText(tpl["prompt"])
                    self._ask_input.setFocus()
                    return

    def _ask_manage_templates(self) -> None:
        """打开模板管理对话框，允许用户增删改快捷提问模板。"""
        dlg = QDialog(self._mw)
        dlg.setWindowTitle("管理快捷提问模板")
        dlg.setMinimumSize(480, 360)
        dlg.setObjectName("cls_ask_template_dialog")
        layout = QVBoxLayout(dlg)

        list_widget = QListWidget()
        list_widget.setObjectName("cls_ask_template_list")
        templates_copy = [dict(t) for t in self._ask_templates]
        for tpl in templates_copy:
            list_widget.addItem(f"{tpl['name']}  ─  {tpl['prompt']}")
        layout.addWidget(list_widget, 1)

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

    # ── 候选词面板 ────────────────────────────────────────────────────────

    def _toggle_ask_pending(self) -> None:
        """折叠/展开待审核候选词面板。"""
        if self._ask_pending_table is None:
            return
        visible = self._ask_pending_table.isVisible()
        self._ask_pending_table.setVisible(not visible)
        if self._ask_pending_toggle is not None:
            self._ask_pending_toggle.setText(
                "收起" if not visible else "展开"
            )

    def _ask_make_op_widget(self, row: int) -> QWidget:
        """为指定 store-row 创建操作列按钮 widget（✓ 确认 / ✗ 丢弃）。"""
        op_widget = QWidget()
        op_layout = QHBoxLayout(op_widget)
        op_layout.setContentsMargins(0, 0, 0, 0)
        op_layout.setSpacing(4)

        confirm_icon_path = get_icon_path("confirm")
        btn_confirm = QPushButton()
        btn_confirm.setObjectName("cls_round_confirm")
        if confirm_icon_path:
            btn_confirm.setIcon(QIcon(str(confirm_icon_path)))
        else:
            btn_confirm.setText("✓")
        btn_confirm.setToolTip("确认导入此词")
        btn_confirm.clicked.connect(lambda _, r=row: self._ask_confirm_single_pending(r))

        discard_icon_path = get_icon_path("discard")
        btn_discard = QPushButton()
        btn_discard.setObjectName("cls_round_discard")
        if discard_icon_path:
            btn_discard.setIcon(QIcon(str(discard_icon_path)))
        else:
            btn_discard.setText("✗")
        btn_discard.setToolTip("丢弃此词")
        btn_discard.clicked.connect(lambda _, r=row: self._ask_discard_single_pending(r))

        op_layout.addWidget(btn_confirm)
        op_layout.addWidget(btn_discard)
        op_widget.setLayout(op_layout)
        return op_widget

    def _ask_render_pending_table(self) -> None:
        """从 store 整体重渲染待审核表格 + 同步批量操作按钮可见性。"""
        if self._ask_pending_table is None:
            return
        self._ask_pending_table.setRowCount(0)
        for row, w in enumerate(self._ask_pending_store):
            self._ask_pending_table.insertRow(row)
            for col, text in enumerate(w.to_view_row()):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self._ask_pending_table.setItem(row, col, item)
            self._ask_pending_table.setCellWidget(row, 5, self._ask_make_op_widget(row))

        non_empty = not self._ask_pending_store.is_empty()
        for btn in (
            self._ask_batch_confirm_btn,
            self._ask_batch_discard_btn,
            self._ask_confirm_selected_btn,
            self._ask_discard_selected_btn,
        ):
            if btn is not None:
                btn.setVisible(non_empty)

    def _ask_batch_confirm_pending(self) -> None:
        """批量确认所有待审核候选词，导入词库。"""
        lang = self._mw._ph_lang
        if not lang or not isinstance(lang, dict):
            QMessageBox.warning(self._mw, "提示", "请先选择一种语言。")
            return

        valid = self._ask_pending_store.valid_words()
        if not valid:
            return

        new_words = [
            NewWord(chinese=w.meaning, conlang=w.conlang, ipa=w.ipa, tts=w.tts, logic=w.style)
            for w in valid
        ]
        self._mw._write_new_words_to_lexicon(new_words, lang)
        self._ask_pending_store.clear()
        self._ask_render_pending_table()
        self._ask_append_chat_message(
            "system", f"✅ {len(new_words)} 个候选词已确认导入词库。"
        )

    def _ask_batch_discard_pending(self) -> None:
        """批量丢弃所有待审核候选词。"""
        count = len(self._ask_pending_store)
        if count == 0:
            return
        reply = QMessageBox.question(
            self._mw, "丢弃确认",
            f"确定丢弃全部 {count} 个候选词？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._ask_pending_store.clear()
        self._ask_render_pending_table()
        self._ask_append_chat_message("system", f"🗑 已丢弃 {count} 个候选词。")

    def _ask_on_table_context_menu(self, pos) -> None:
        """待审核表格右键菜单：复制选中单元格内容。"""
        item = self._ask_pending_table.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self._ask_pending_table)
        copy_action = menu.addAction("复制")
        if menu.exec_(self._ask_pending_table.viewport().mapToGlobal(pos)) == copy_action:
            selected = self._ask_pending_table.selectedItems()
            if selected:
                texts = [s.text() for s in selected]
                QApp.clipboard().setText("\n".join(texts))

    def _ask_clear_pending_table(self) -> None:
        """清空待审核（store + view）。"""
        self._ask_pending_store.clear()
        self._ask_render_pending_table()

    def _ask_confirm_single_pending(self, row: int) -> None:
        """确认导入单条候选词到词库。"""
        word = self._ask_pending_store.get(row)
        if word is None:
            return

        lang = self._mw._ph_lang
        if not lang or not isinstance(lang, dict):
            QMessageBox.warning(self._mw, "提示", "请先选择一种语言。")
            return

        if word.is_valid:
            nw = NewWord(
                chinese=word.meaning,
                conlang=word.conlang,
                ipa=word.ipa,
                tts=word.tts,
                logic=word.style,
            )
            self._mw._write_new_words_to_lexicon([nw], lang)

        self._ask_pending_store.remove_at(row)
        self._ask_render_pending_table()
        self._ask_append_chat_message(
            "system", f"✅ 候选词「{word.label()}」已确认导入词库。"
        )

    def _ask_discard_single_pending(self, row: int) -> None:
        """丢弃单条候选词。"""
        word = self._ask_pending_store.remove_at(row)
        if word is None:
            return
        self._ask_render_pending_table()
        self._ask_append_chat_message("system", f"🗑 已丢弃候选词「{word.label()}」。")

    def _ask_confirm_selected_pending(self) -> None:
        """确认导入选中行的候选词到词库。"""
        if self._ask_pending_table is None:
            return
        lang = self._mw._ph_lang
        if not lang or not isinstance(lang, dict):
            QMessageBox.warning(self._mw, "提示", "请先选择一种语言。")
            return

        selected_rows = sorted(
            set(idx.row() for idx in self._ask_pending_table.selectedIndexes())
        )
        if not selected_rows:
            self._mw.statusBar().showMessage("请先在表格中选择要确认的候选词", 3000)
            return

        selected_words = [
            self._ask_pending_store[r]
            for r in selected_rows
            if 0 <= r < len(self._ask_pending_store)
        ]
        valid_words = [w for w in selected_words if w.is_valid]
        new_words = [
            NewWord(chinese=w.meaning, conlang=w.conlang, ipa=w.ipa, tts=w.tts, logic=w.style)
            for w in valid_words
        ]

        if new_words:
            self._mw._write_new_words_to_lexicon(new_words, lang)

        self._ask_pending_store.remove_indices(selected_rows)
        self._ask_render_pending_table()
        self._ask_append_chat_message(
            "system", f"✅ {len(new_words)} 个选中候选词已确认导入词库。"
        )

    def _ask_discard_selected_pending(self) -> None:
        """丢弃选中行的候选词。"""
        if self._ask_pending_table is None:
            return
        selected_rows = sorted(
            set(idx.row() for idx in self._ask_pending_table.selectedIndexes())
        )
        if not selected_rows:
            self._mw.statusBar().showMessage("请先在表格中选择要丢弃的候选词", 3000)
            return

        count = len(selected_rows)
        reply = QMessageBox.question(
            self._mw, "丢弃确认",
            f"确定丢弃选中的 {count} 个候选词？此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        removed = self._ask_pending_store.remove_indices(selected_rows)
        self._ask_render_pending_table()
        self._ask_append_chat_message(
            "system", f"🗑 已丢弃 {len(removed)} 个选中候选词。"
        )

    # ── 工具方法 ──────────────────────────────────────────────────────────

    def _ask_append_chat_message(self, role: str, content: str) -> None:
        """向对话历史区追加一条消息。"""
        if self._ask_chat_display is None:
            return
        if role == "user":
            label = "你"
            color_token = theme_manager.token("color_text_primary")
        elif role == "ai":
            label = "DUD"
            color_token = "#6B6880"
        else:
            label = "系统"
            color_token = theme_manager.token("color_text_secondary")
        self._ask_chat_display.append(
            f'<p style="margin:4px 0;"><b style="color:{color_token};">{label}：</b>{content}</p>'
        )

    def _estimate_tokens(self, text: str) -> int:
        """粗略估算文本的 Token 数量（中文字符 ≈2 token，英文单词 ≈1 token）。"""
        cn_chars = sum(1 for c in text if '一' <= c <= '鿿')
        en_chars = len(text) - cn_chars
        return int(cn_chars * 2 + en_chars * 0.25)

    def _ask_update_token_display(self) -> None:
        """更新 Token 圆圈和标签：估算当前对话总 Token 并显示使用率。"""
        total_text = "".join(m.get("content", "") for m in self._ask_messages)
        estimated = self._estimate_tokens(total_text)
        context_limit = 8192
        model = str(self._mw.state.get("paperhub_model", "qwen3-max"))
        if "128" in model:
            context_limit = 128000
        elif "32" in model:
            context_limit = 32000
        elif "max" in model or "pro" in model:
            context_limit = 32000

        ratio = estimated / context_limit if context_limit > 0 else 0.0

        if self._ask_token_circle is not None:
            self._ask_token_circle.set_ratio(ratio)
            msg_count = len(self._ask_messages)
            self._ask_token_circle.setToolTip(
                f"消息 {msg_count} 条 · ~{estimated} / {context_limit} Token"
            )
