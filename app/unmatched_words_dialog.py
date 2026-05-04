"""
未匹配词汇处理对话框（阶段七）。

当翻译完成后有未匹配词汇时弹出，提供：
  - 表格显示所有未匹配词汇
  - 每行可手动填写自创语和 TTS 拼写
  - 每行有 [手动] / [AI] 按钮：AI 调用 PaperHub 为该词生成翻译
  - [全部 AI 生成]：批量调用 PaperHub AI 翻译所有未匹配词
  - [全部手动填写]：清空 AI 填写，让用户手动输入
  - [跳过]：关闭对话框，不保存
  - [保存到词库]：将填写的内容追加到词库

公开接口：
  UnmatchedWordsDialog(unmatched_words, bundle, paperhub_settings, parent)
  get_entries() -> List[UnmatchedWordEntry]
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QThread, Qt, pyqtSignal
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

from app.paperhub_client import (
    _call_paperhub_chat,
    _extract_json_from_response,
    _get_settings_params,
    _whitepaper_full,
    _vocabulary_list,
)
from app.ui_theme import theme_manager


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class UnmatchedWordEntry:
    """一条未匹配词汇的处理结果。"""
    chinese: str
    conlang: str = ""
    ipa: str = ""
    tts: str = ""
    logic: str = ""
    created_by: str = ""       # "manual" | "paperhub_ai"
    created_time: str = ""     # ISO 8601
    model: str = ""            # AI 模型名


# ---------------------------------------------------------------------------
# AI 单词生成线程
# ---------------------------------------------------------------------------

class _WordAIThread(QThread):
    """后台线程：为单个词汇调用 PaperHub AI 生成翻译。"""

    finished = pyqtSignal(str, str, object)  # (chinese_word, error_msg, UnmatchedWordEntry | None)

    def __init__(
        self,
        chinese_word: str,
        bundle: Dict[str, Any],
        paperhub_settings: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._chinese_word = chinese_word
        self._bundle = bundle
        self._paperhub_settings = paperhub_settings

    def run(self) -> None:
        try:
            entry = generate_word(self._chinese_word, self._bundle, self._paperhub_settings)
            self.finished.emit(self._chinese_word, "", entry)
        except Exception as exc:
            self.finished.emit(self._chinese_word, str(exc), None)


class _BatchAIThread(QThread):
    """后台线程：批量调用 PaperHub AI 翻译所有未匹配词。"""

    finished = pyqtSignal(str, object)  # (error_msg, List[UnmatchedWordEntry] | None)

    def __init__(
        self,
        chinese_words: List[str],
        bundle: Dict[str, Any],
        paperhub_settings: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._chinese_words = chinese_words
        self._bundle = bundle
        self._paperhub_settings = paperhub_settings

    def run(self) -> None:
        try:
            entries = generate_batch_words(self._chinese_words, self._bundle, self._paperhub_settings)
            self.finished.emit("", entries)
        except Exception as exc:
            self.finished.emit(str(exc), None)


# ---------------------------------------------------------------------------
# PaperHub AI 单词生成接口
# ---------------------------------------------------------------------------

def generate_word(
    chinese_word: str,
    bundle: Dict[str, Any],
    paperhub_settings: Dict[str, Any],
) -> UnmatchedWordEntry:
    """
    为单个中文词汇调用 PaperHub AI 生成自创语翻译。

    返回 UnmatchedWordEntry，包含 conlang, ipa, tts, logic 等字段。
    """
    params = _get_settings_params(paperhub_settings)
    api_key = params["api_key"]

    if not api_key:
        raise ValueError("未填写 PaperHub API Key，请在「设置 → PaperHub 设置」中配置。")

    # ── 系统提示词：使用阶段七专用模板（与用户规格一致）──
    whitepaper = _whitepaper_full(bundle)
    vocab_samples = _vocabulary_samples_for_prompt(bundle)

    system_prompt = (
        "你是一个虚构语言专家。请根据以下语言白皮书为中文词汇创造对应的自创语。\n"
        "\n【语言白皮书】\n"
        + whitepaper
        + "\n\n【已有词库示例】（参考风格）\n"
        + vocab_samples
        + "\n\n【翻译规则】\n"
        "新词必须符合白皮书中的音位表\n"
        "新词的构词逻辑应与已有词汇风格一致\n"
        "输出格式必须为JSON"
    )

    # ── 用户提示词：单个词汇 JSON 格式 ──
    user_prompt = (
        f"请为以下中文词汇创造自创语：\n"
        f"词汇：{chinese_word}\n\n"
        "请按以下JSON格式输出（不要输出任何其他内容，不要加markdown标记）：\n"
        "{\n"
        "  \"chinese\": \"中文原词\",\n"
        "  \"conlang\": \"自创语\",\n"
        "  \"ipa\": \"IPA音标\",\n"
        "  \"tts\": \"TTS友好拼写\",\n"
        "  \"logic\": \"构词逻辑简要说明\"\n"
        "}"
    )

    raw = _call_paperhub_chat(
        api_key=api_key,
        base_url=params["base_url"],
        model=params["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=params["temperature"],
        max_tokens=params["max_tokens"],
        reasoning_enabled=params["reasoning"],
        timeout=45,
    )

    # 解析 JSON 响应
    data = _extract_json_from_response(raw)

    if data is None:
        raise ValueError(f"AI 响应无法解析为 JSON。原始响应：\n{raw[:300]}")

    conlang = str(data.get("conlang") or data.get("自创语") or "").strip()
    ipa = str(data.get("ipa") or data.get("IPA") or "").strip()
    tts = str(data.get("tts") or data.get("TTS") or "").strip()
    logic = str(data.get("logic") or data.get("构词逻辑") or data.get("构词逻辑说明") or "").strip()

    if not conlang:
        raise ValueError(f"AI 未生成自创语翻译。原始响应：\n{raw[:300]}")

    now = datetime.now().isoformat(timespec="seconds")

    return UnmatchedWordEntry(
        chinese=chinese_word,
        conlang=conlang,
        ipa=ipa,
        tts=tts or conlang,
        logic=logic,
        created_by="paperhub_ai",
        created_time=now,
        model=params["model"],
    )


def generate_batch_words(
    chinese_words: List[str],
    bundle: Dict[str, Any],
    paperhub_settings: Dict[str, Any],
) -> List[UnmatchedWordEntry]:
    """
    批量调用 PaperHub AI 为多个中文词汇生成自创语翻译。

    为避免多次 API 调用，将多个词汇合并为一个请求。
    """
    params = _get_settings_params(paperhub_settings)
    api_key = params["api_key"]

    if not api_key:
        raise ValueError("未填写 PaperHub API Key，请在「设置 → PaperHub 设置」中配置。")

    # ── 系统提示词：使用阶段七专用模板（与用户规格一致）──
    whitepaper = _whitepaper_full(bundle)
    vocab_samples = _vocabulary_samples_for_prompt(bundle)

    system_prompt = (
        "你是一个虚构语言专家。请根据以下语言白皮书为中文词汇创造对应的自创语。\n"
        "\n【语言白皮书】\n"
        + whitepaper
        + "\n\n【已有词库示例】（参考风格）\n"
        + vocab_samples
        + "\n\n【翻译规则】\n"
        "新词必须符合白皮书中的音位表\n"
        "新词的构词逻辑应与已有词汇风格一致\n"
        "输出格式必须为JSON数组"
    )

    # ── 用户提示词：批量词汇 JSON 数组格式 ──
    words_list = "、".join(chinese_words)
    user_prompt = (
        f"请为以下中文词汇列表创造对应的自创语（JSON数组格式）：\n"
        f"词汇列表：{words_list}\n\n"
        "请按以下JSON格式输出（不要输出任何其他内容，不要加markdown标记）：\n"
        "[\n"
        "  {\n"
        "    \"chinese\": \"词\",\n"
        "    \"conlang\": \"自创语\",\n"
        "    \"ipa\": \"IPA音标\",\n"
        "    \"tts\": \"TTS友好拼写\",\n"
        "    \"logic\": \"构词逻辑简要说明\"\n"
        "  },\n"
        "  ...\n"
        "]"
    )

    raw = _call_paperhub_chat(
        api_key=api_key,
        base_url=params["base_url"],
        model=params["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=params["temperature"],
        max_tokens=min(params["max_tokens"], 8192),
        reasoning_enabled=params["reasoning"],
        timeout=60,
    )

    # 解析 JSON 数组响应
    data = _extract_json_from_response(raw)

    if data is None:
        raise ValueError(f"AI 响应无法解析为 JSON。原始响应：\n{raw[:300]}")

    # data 可能是 list（直接数组）或 dict（含包装字段）
    items_raw: List[Dict] = []
    if isinstance(data, list):
        items_raw = data
    elif isinstance(data, dict):
        # 尝试从包装字段中提取数组
        for key in ("words", "results", "vocabulary", "new_words", "entries"):
            val = data.get(key)
            if isinstance(val, list):
                items_raw = val
                break
        if not items_raw:
            # 单个对象包装
            items_raw = [data]

    entries: List[UnmatchedWordEntry] = []
    now = datetime.now().isoformat(timespec="seconds")

    for item in items_raw:
        if not isinstance(item, dict):
            continue
        chinese = str(item.get("chinese") or item.get("中文") or "").strip()
        conlang = str(item.get("conlang") or item.get("自创语") or "").strip()
        ipa = str(item.get("ipa") or item.get("IPA") or "").strip()
        tts = str(item.get("tts") or item.get("TTS") or "").strip()
        logic = str(item.get("logic") or item.get("构词逻辑") or item.get("构词逻辑说明") or "").strip()

        if not chinese or not conlang:
            continue

        # 匹配到请求中的某个词（AI 可能返回与输入不完全一致的中文）
        matched_word = chinese
        for w in chinese_words:
            if w == chinese or chinese.startswith(w) or w.startswith(chinese):
                matched_word = w
                break

        entries.append(UnmatchedWordEntry(
            chinese=matched_word,
            conlang=conlang,
            ipa=ipa,
            tts=tts or conlang,
            logic=logic,
            created_by="paperhub_ai",
            created_time=now,
            model=params["model"],
        ))

    # 补全：如果某些输入词未在 AI 响应中出现，保留为空
    covered = {e.chinese for e in entries}
    for w in chinese_words:
        if w not in covered:
            entries.append(UnmatchedWordEntry(chinese=w))

    return entries


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

def _vocabulary_samples_for_prompt(bundle: Dict[str, Any], max_items: int = 30) -> str:
    """提取词库样本，供 AI 单词生成参考风格（复用 paperhub_client 的格式化逻辑）。"""
    return _vocabulary_list(bundle, max_items=max_items)


# ---------------------------------------------------------------------------
# 对话框
# ---------------------------------------------------------------------------

class UnmatchedWordsDialog(QDialog):
    """未匹配词汇处理对话框（阶段七）。"""

    def __init__(
        self,
        unmatched_words: List[str],
        bundle: Dict[str, Any],
        paperhub_settings: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.unmatched_words = list(unmatched_words)
        self.bundle = bundle
        self.paperhub_settings = paperhub_settings

        # 内部数据：每条未匹配词汇对应一个 UnmatchedWordEntry
        self._entries: Dict[str, UnmatchedWordEntry] = {}
        for w in self.unmatched_words:
            self._entries[w] = UnmatchedWordEntry(chinese=w)

        # AI 线程引用
        self._ai_thread: Optional[QThread] = None

        self.setWindowTitle("未匹配词汇处理")
        self.setMinimumWidth(620)
        self.setMinimumHeight(360)
        self.resize(720, 400)
        self._build_ui()

    # -- UI 构建 --

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 标题提示
        hint = QLabel(
            "以下词汇在词库中未找到，请手动填写或使用 AI 生成自创语翻译后保存到词库。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 表格
        self._table = QTableWidget(len(self.unmatched_words), 4)
        self._table.setHorizontalHeaderLabels(["中文", "自创语", "TTS拼写", "操作"])
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)

        for row_idx, word in enumerate(self.unmatched_words):
            # 中文（不可编辑）
            chinese_item = QTableWidgetItem(word)
            chinese_item.setFlags(chinese_item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(row_idx, 0, chinese_item)

            # 自创语（可编辑）
            conlang_item = QTableWidgetItem("")
            self._table.setItem(row_idx, 1, conlang_item)

            # TTS 拼写（可编辑）
            tts_item = QTableWidgetItem("")
            self._table.setItem(row_idx, 2, tts_item)

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(2, 2, 2, 2)
            btn_layout.setSpacing(4)

            btn_manual = QPushButton("手动")
            btn_manual.setFixedWidth(48)
            btn_manual.setToolTip("手动填写此词的自创语和 TTS 拼写")
            btn_manual.clicked.connect(lambda _, w=word: self._on_manual_fill(w))

            btn_ai = QPushButton("AI")
            btn_ai.setFixedWidth(48)
            btn_ai.setToolTip("调用 PaperHub AI 为此词生成自创语翻译")
            btn_ai.clicked.connect(lambda _, w=word: self._on_ai_single(w))

            btn_layout.addWidget(btn_manual)
            btn_layout.addWidget(btn_ai)
            btn_layout.addStretch(1)

            self._table.setCellWidget(row_idx, 3, btn_widget)

        layout.addWidget(self._table, 1)

        # 状态提示
        self._status_label = QLabel("")
        self._status_label.setProperty("class", "secondary")
        layout.addWidget(self._status_label)

        # 底部按钮行
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self._btn_batch_ai = QPushButton("全部 AI 生成")
        self._btn_batch_ai.setMinimumWidth(110)
        self._btn_batch_ai.setToolTip("批量调用 PaperHub AI 翻译所有未匹配词")
        self._btn_batch_ai.clicked.connect(self._on_batch_ai)

        btn_clear_ai = QPushButton("全部手动填写")
        btn_clear_ai.setMinimumWidth(110)
        btn_clear_ai.setToolTip("清空 AI 填写的内容，让用户手动输入")
        btn_clear_ai.clicked.connect(self._on_clear_all)

        btn_skip = QPushButton("跳过")
        btn_skip.setMinimumWidth(60)
        btn_skip.setToolTip("跳过，不保存任何内容")
        btn_skip.clicked.connect(self.reject)

        self._btn_save = QPushButton("保存到词库")
        self._btn_save.setMinimumWidth(110)
        self._btn_save.setToolTip("将填写的内容追加到主词库和映射表")
        self._btn_save.clicked.connect(self._on_save)

        btn_row.addWidget(self._btn_batch_ai)
        btn_row.addWidget(btn_clear_ai)
        btn_row.addWidget(btn_skip)
        btn_row.addWidget(self._btn_save)

        layout.addLayout(btn_row)

    # -- 手动填写 --

    def _on_manual_fill(self, word: str) -> None:
        """将焦点跳转到该行的自创语编辑列。"""
        row = self.unmatched_words.index(word)
        self._table.setCurrentCell(row, 1)
        self._table.editItem(self._table.item(row, 1))

    # -- AI 单词生成 --

    def _on_ai_single(self, word: str) -> None:
        """为单个词汇调用 PaperHub AI 生成翻译。"""
        # 防止重复点击
        if self._ai_thread is not None and self._ai_thread.isRunning():
            self._status_label.setText("AI 正在生成中，请等待完成…")
            return

        # 检查 API Key
        api_key = str(self.paperhub_settings.get("paperhub_api_key") or "").strip()
        if not api_key:
            QMessageBox.warning(
                self, "PaperHub 未配置",
                "未填写 PaperHub API Key，请在「设置 → PaperHub 设置」中配置。",
            )
            return

        self._status_label.setText(f"正在为「{word}」生成 AI 翻译…")
        self._btn_batch_ai.setEnabled(False)
        self._btn_save.setEnabled(False)

        self._ai_thread = _WordAIThread(word, self.bundle, self.paperhub_settings, self)
        self._ai_thread.finished.connect(self._on_ai_single_finished)
        self._ai_thread.finished.connect(self._ai_thread.deleteLater)
        self._ai_thread.start()

    def _on_ai_single_finished(
        self,
        chinese_word: str,
        error_msg: str,
        entry: Optional[UnmatchedWordEntry],
    ) -> None:
        """AI 单词生成完成回调。"""
        self._btn_batch_ai.setEnabled(True)
        self._btn_save.setEnabled(True)

        if error_msg or entry is None:
            self._status_label.setText(f"「{chinese_word}」AI 生成失败：{error_msg}")
            QMessageBox.warning(
                self, "AI 生成失败",
                f"词汇「{chinese_word}」的 AI 翻译生成失败：\n{error_msg}",
            )
            return

        # 更新内部数据与表格
        self._entries[chinese_word] = entry
        row = self.unmatched_words.index(chinese_word)

        conlang_item = self._table.item(row, 1)
        if conlang_item is not None:
            conlang_item.setText(entry.conlang)
            # AI 生成的行用淡蓝色标记
            conlang_item.setBackground(Qt.GlobalColor.cyan.lighter(160))

        tts_item = self._table.item(row, 2)
        if tts_item is not None:
            tts_item.setText(entry.tts)
            tts_item.setBackground(Qt.GlobalColor.cyan.lighter(160))

        self._status_label.setText(f"「{chinese_word}」AI 翻译已生成：{entry.conlang}")

    # -- 批量 AI 生成 --

    def _on_batch_ai(self) -> None:
        """批量调用 PaperHub AI 翻译所有未匹配词。"""
        if self._ai_thread is not None and self._ai_thread.isRunning():
            self._status_label.setText("AI 正在生成中，请等待完成…")
            return

        # 检查 API Key
        api_key = str(self.paperhub_settings.get("paperhub_api_key") or "").strip()
        if not api_key:
            QMessageBox.warning(
                self, "PaperHub 未配置",
                "未填写 PaperHub API Key，请在「设置 → PaperHub 设置」中配置。",
            )
            return

        self._status_label.setText(f"正在批量 AI 生成 {len(self.unmatched_words)} 个词汇…")
        self._btn_batch_ai.setEnabled(False)
        self._btn_save.setEnabled(False)

        self._ai_thread = _BatchAIThread(
            self.unmatched_words, self.bundle, self.paperhub_settings, self
        )
        self._ai_thread.finished.connect(self._on_batch_ai_finished)
        self._ai_thread.finished.connect(self._ai_thread.deleteLater)
        self._ai_thread.start()

    def _on_batch_ai_finished(
        self,
        error_msg: str,
        entries: Optional[List[UnmatchedWordEntry]],
    ) -> None:
        """批量 AI 生成完成回调。"""
        self._btn_batch_ai.setEnabled(True)
        self._btn_save.setEnabled(True)

        if error_msg or entries is None:
            self._status_label.setText(f"批量 AI 生成失败：{error_msg}")
            QMessageBox.warning(
                self, "AI 生成失败",
                f"批量 AI 翻译生成失败：\n{error_msg}",
            )
            return

        # 更新内部数据与表格
        for entry in entries:
            self._entries[entry.chinese] = entry
            try:
                row = self.unmatched_words.index(entry.chinese)
            except ValueError:
                continue

            if entry.conlang:
                conlang_item = self._table.item(row, 1)
                if conlang_item is not None:
                    conlang_item.setText(entry.conlang)
                    conlang_item.setBackground(Qt.GlobalColor.cyan.lighter(160))

                tts_item = self._table.item(row, 2)
                if tts_item is not None:
                    tts_item.setText(entry.tts)
                    tts_item.setBackground(Qt.GlobalColor.cyan.lighter(160))

        count = sum(1 for e in entries if e.conlang)
        self._status_label.setText(
            f"批量 AI 生成完成，{count}/{len(self.unmatched_words)} 个词汇已生成翻译。"
        )

    # -- 清空 / 全部手动 --

    def _on_clear_all(self) -> None:
        """清空所有 AI 填写的内容，让用户手动输入。"""
        for row_idx, word in enumerate(self.unmatched_words):
            entry = self._entries[word]
            entry.conlang = ""
            entry.ipa = ""
            entry.tts = ""
            entry.logic = ""
            entry.created_by = "manual"
            entry.created_time = ""
            entry.model = ""

            conlang_item = self._table.item(row_idx, 1)
            if conlang_item is not None:
                conlang_item.setText("")
                conlang_item.setBackground(Qt.GlobalColor.white)

            tts_item = self._table.item(row_idx, 2)
            if tts_item is not None:
                tts_item.setText("")
                tts_item.setBackground(Qt.GlobalColor.white)

        self._status_label.setText("已清空所有内容，请手动填写。")

    # -- 保存到词库 --

    def _on_save(self) -> None:
        """收集表格数据，构造 UnmatchedWordEntry 列表，返回 Accepted。"""
        # 先从表格读取用户手动编辑的内容，覆盖 AI 生成结果
        for row_idx, word in enumerate(self.unmatched_words):
            entry = self._entries[word]

            conlang_item = self._table.item(row_idx, 1)
            if conlang_item is not None:
                user_conlang = conlang_item.text().strip()
                if user_conlang:
                    # 如果用户修改了 AI 生成的内容，标记为 manual（比较必须在赋值之前）
                    if entry.created_by == "paperhub_ai" and user_conlang != entry.conlang:
                        entry.created_by = "manual_ai_modified"
                    entry.conlang = user_conlang

            tts_item = self._table.item(row_idx, 2)
            if tts_item is not None:
                user_tts = tts_item.text().strip()
                if user_tts:
                    entry.tts = user_tts
                elif entry.conlang and not entry.tts:
                    entry.tts = entry.conlang

            # 手动填写的词也记录时间
            if entry.conlang and not entry.created_by:
                entry.created_by = "manual"
                entry.created_time = datetime.now().isoformat(timespec="seconds")

        # 检查是否有填写内容
        filled = [e for e in self._entries.values() if e.conlang]
        if not filled:
            QMessageBox.information(
                self, "提示",
                "没有填写任何词汇的翻译，请先填写或使用 AI 生成。",
            )
            return

        self.accept()

    def get_entries(self) -> List[UnmatchedWordEntry]:
        """返回最终的处理结果列表。"""
        # 最终从表格读取所有用户编辑
        for row_idx, word in enumerate(self.unmatched_words):
            entry = self._entries[word]
            conlang_item = self._table.item(row_idx, 1)
            if conlang_item is not None:
                text = conlang_item.text().strip()
                if text:
                    entry.conlang = text
            tts_item = self._table.item(row_idx, 2)
            if tts_item is not None:
                text = tts_item.text().strip()
                if text:
                    entry.tts = text
                elif entry.conlang and not entry.tts:
                    entry.tts = entry.conlang

        return [self._entries[w] for w in self.unmatched_words]