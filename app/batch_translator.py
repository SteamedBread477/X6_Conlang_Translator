"""
批量翻译引擎（阶段八）。

基于 Excel 台本数据，执行批量翻译：
  - 规则模式：逐行调用 translate_multiline_rule
  - 混合模式：词库优先，未匹配部分用 PaperHub AI 补全
  - AI 模式：全部用 PaperHub AI 翻译

并发控制：
  - 使用 QThread 避免阻塞 UI
  - 通过信号报告进度和完成状态
  - 并发请求数和间隔由 BatchTranslateSettings 控制

公开接口：
  BatchTranslateWorker(QThread) — 后台翻译线程
  BatchTranslateResult — 单行翻译结果
"""
from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from app.batch_translate_dialog import BatchTranslateSettings
from app.excel_import import ExcelRow
from app.paperhub_client import (
    NewWord,
    PaperHubResult,
    PaperHubError,
    translate_with_paperhub,
    _get_settings_params,
)
from app.rule_translator import RuleTranslationResult, translate_multiline_rule
from app.unmatched_words_dialog import UnmatchedWordEntry


# --------------------------------------------------------------------------- 
# 数据结构
# --------------------------------------------------------------------------- 

@dataclass
class BatchTranslateResult:
    """单行翻译结果。"""
    row_index: int = 0
    row_id: str = ""           # 台本ID
    character: str = ""        # Character
    emotion: str = ""          # Emotion
    scene_context: str = ""    # Scene_Context
    chinese_text: str = ""     # Text（原文）
    conlang: str = ""          # 自创语翻译
    tts: str = ""              # TTS 音译
    mode_used: str = ""        # 实际使用的翻译模式
    unmatched_words: List[str] = field(default_factory=list)
    new_words: List[NewWord] = field(default_factory=list)
    error: str = ""


# --------------------------------------------------------------------------- 
# 后台翻译线程
# --------------------------------------------------------------------------- 

class BatchTranslateWorker(QThread):
    """
    后台批量翻译线程。

    信号：
      progress(row_index, total_rows, result) — 每行翻译完成
      finished(results, unmatched_entries, error_msg) — 全部完成
    """

    progress = pyqtSignal(int, int, object)       # (row_index, total, BatchTranslateResult)
    finished = pyqtSignal(list, list, str)         # (results, unmatched_entries, error_msg)

    def __init__(
        self,
        rows: List[ExcelRow],
        settings: BatchTranslateSettings,
        bundle: Dict[str, Any],
        paperhub_settings: Dict[str, Any],
        parent: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self._rows = rows
        self._settings = settings
        self._bundle = bundle
        self._paperhub_settings = paperhub_settings
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        """执行批量翻译。"""
        results: List[BatchTranslateResult] = []
        all_unmatched: List[UnmatchedWordEntry] = []
        all_new_words: List[NewWord] = []
        total = len(self._rows)
        error_msg = ""

        lexicon = self._bundle.get("lexicon") or {}
        if not isinstance(lexicon, dict):
            lexicon = {}
        lexicon = {str(k): str(v) for k, v in lexicon.items() if str(k).strip()}

        tts_map = self._bundle.get("tts_map") or {}
        if not isinstance(tts_map, dict):
            tts_map = {}
        tts_map = {str(k): str(v) for k, v in tts_map.items() if str(k).strip()}

        for idx, row in enumerate(self._rows):
            if self._cancelled:
                error_msg = "用户取消了翻译。"
                break

            chinese_text = row.data.get("Text", "").strip()
            row_id = row.data.get("台本ID", "")
            character = row.data.get("Character", "")
            emotion = row.data.get("Emotion", "")
            scene_context = row.data.get("Scene_Context", "")

            result = BatchTranslateResult(
                row_index=idx,
                row_id=row_id,
                character=character,
                emotion=emotion,
                scene_context=scene_context,
                chinese_text=chinese_text,
            )

            if not chinese_text:
                # 空行直接跳过
                result.conlang = ""
                result.tts = ""
                result.mode_used = "skip"
                results.append(result)
                self.progress.emit(idx, total, result)
                continue

            # ── 规则翻译 ──────────────────────────────────────────
            rule_result: Optional[RuleTranslationResult] = None
            try:
                rule_result = translate_multiline_rule(chinese_text, lexicon, tts_map)
            except Exception as exc:
                result.error = f"规则翻译失败：{exc}"
                result.mode_used = "rule_error"
                results.append(result)
                self.progress.emit(idx, total, result)
                continue

            # ── 根据模式决定是否调用 AI ──────────────────────────
            mode = self._settings.mode

            if mode == "rule":
                # 纯规则翻译
                result.conlang = rule_result.conlang
                result.tts = rule_result.phonetic
                result.unmatched_words = rule_result.unmatched_words
                result.mode_used = "rule"

            elif mode == "hybrid":
                # 词库优先，未匹配部分用 AI
                if rule_result.unmatched_words:
                    # 有未匹配词，调用 AI 补全
                    ai_result = self._call_ai_translate(chinese_text)
                    if ai_result and not ai_result.error:
                        # 使用 AI 补全结果
                        result.conlang = ai_result.conlang
                        result.tts = ai_result.tts
                        result.unmatched_words = []
                        result.new_words = ai_result.new_words
                        all_new_words.extend(ai_result.new_words)
                        result.mode_used = "hybrid_ai"
                    else:
                        # AI 失败，回退到规则结果
                        result.conlang = rule_result.conlang
                        result.tts = rule_result.phonetic
                        result.unmatched_words = rule_result.unmatched_words
                        if ai_result and ai_result.error:
                            result.error = ai_result.error
                        result.mode_used = "hybrid_rule_fallback"
                else:
                    # 词库全覆盖，不需要 AI
                    result.conlang = rule_result.conlang
                    result.tts = rule_result.phonetic
                    result.unmatched_words = []
                    result.mode_used = "hybrid_rule_only"

            elif mode == "ai":
                # 全部 AI 翻译
                ai_result = self._call_ai_translate(chinese_text)
                if ai_result and not ai_result.error:
                    result.conlang = ai_result.conlang
                    result.tts = ai_result.tts
                    result.new_words = ai_result.new_words
                    all_new_words.extend(ai_result.new_words)
                    result.mode_used = "ai"
                else:
                    # AI 失败，回退到规则翻译
                    result.conlang = rule_result.conlang
                    result.tts = rule_result.phonetic
                    result.unmatched_words = rule_result.unmatched_words
                    if ai_result and ai_result.error:
                        result.error = ai_result.error
                    result.mode_used = "ai_rule_fallback"

            # 收集未匹配词（用于报告 / 自动添加）
            for w in result.unmatched_words:
                now = datetime.now().isoformat(timespec="seconds")
                all_unmatched.append(UnmatchedWordEntry(
                    chinese=w,
                    created_by="batch_unmatched",
                    created_time=now,
                    model=self._settings.model,
                ))

            results.append(result)
            self.progress.emit(idx, total, result)

            # 请求间隔（避免限流）
            if mode != "rule" and idx < total - 1:
                interval = self._settings.request_interval
                if interval > 0:
                    time.sleep(interval)

        # ── 自动添加新词到词库 ────────────────────────────────────
        if self._settings.auto_add_new_words and all_new_words and not self._cancelled:
            self._auto_add_new_words(all_new_words)

        self.finished.emit(results, all_unmatched, error_msg)

    def _call_ai_translate(self, text: str) -> Optional[PaperHubResult]:
        """调用 PaperHub AI 翻译，带错误处理。"""
        # 构建带当前设置的翻译参数
        ph_settings = dict(self._paperhub_settings)
        ph_settings["paperhub_strategy"] = "always"  # 批量时用 always 策略
        ph_settings["paperhub_model"] = self._settings.model
        ph_settings["paperhub_reasoning_enabled"] = self._settings.reasoning_enabled

        try:
            return translate_with_paperhub(ph_settings, self._bundle, text)
        except PaperHubError as exc:
            return PaperHubResult(error=exc.user_hint)
        except Exception as exc:
            return PaperHubResult(error=str(exc))

    def _auto_add_new_words(self, new_words: List[NewWord]) -> None:
        """自动将 AI 创造的新词追加到主词库和映射表。"""
        # 获取语言目录路径（从 bundle 中）
        master_path = self._bundle.get("master_library_path")
        mapping_path = self._bundle.get("mapping_rules_path")

        if not master_path or not mapping_path:
            return

        # ── 写入主词库 ────────────────────────────────────────────
        master_file = Path(master_path)
        try:
            if master_file.is_file():
                with master_file.open("r", encoding="utf-8") as fh:
                    master_data = json.load(fh)
            else:
                master_data = {}

            # 确保 vocabulary 键存在
            vocab = master_data.get("vocabulary")
            if vocab is None:
                vocab = {}
                master_data["vocabulary"] = vocab

            # 简单中文→自创语映射（顶层，供 rule_translator 兼容）
            simple_map = {}
            if isinstance(master_data, dict):
                for k, v in master_data.items():
                    if k != "vocabulary" and isinstance(v, str):
                        simple_map[k] = v

            now = datetime.now().isoformat(timespec="seconds")
            for nw in new_words:
                if nw.chinese and nw.conlang:
                    # 顶层简单映射
                    simple_map[nw.chinese] = nw.conlang
                    # vocabulary 富元数据
                    vocab[nw.chinese] = {
                        "conlang": nw.conlang,
                        "ipa": nw.ipa,
                        "tts": nw.tts or nw.conlang,
                        "logic": nw.logic,
                        "created_by": "paperhub_ai",
                        "created_time": now,
                        "model": self._settings.model,
                    }

            # 合并顶层简单映射与 vocabulary
            master_data["vocabulary"] = vocab
            for k, v in simple_map.items():
                master_data[k] = v

            with master_file.open("w", encoding="utf-8") as fh:
                json.dump(master_data, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass  # 静默失败，不影响翻译流程

        # ── 写入映射表 CSV ────────────────────────────────────────
        mapping_file = Path(mapping_path)
        try:
            existing_rows: List[List[str]] = []
            existing_words: set = set()

            if mapping_file.is_file():
                with mapping_file.open("r", encoding="utf-8-sig") as fh:
                    reader = csv.reader(fh)
                    header = next(reader, None)
                    if header:
                        existing_rows.append(header)
                    for row_data in reader:
                        if row_data:
                            existing_rows.append(row_data)
                            if len(row_data) >= 1:
                                existing_words.add(row_data[0].strip())

            for nw in new_words:
                if nw.chinese and nw.conlang and nw.conlang not in existing_words:
                    existing_rows.append([nw.conlang, nw.ipa, nw.tts or nw.conlang])
                    existing_words.add(nw.conlang)

            with mapping_file.open("w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerows(existing_rows)
        except Exception:
            pass  # 静默失败


# --------------------------------------------------------------------------- 
# 导出功能
# --------------------------------------------------------------------------- 

def export_results_to_excel(
    results: List[BatchTranslateResult],
    original_rows: List[ExcelRow],
    output_path: str,
) -> bool:
    """将翻译结果导出为 Excel 文件（在原数据基础上增加翻译列）。"""
    try:
        import pandas as pd
    except ImportError:
        return False

    # 构建导出数据
    rows_out: List[Dict[str, Any]] = []
    for idx, result in enumerate(results):
        # 保留原始列数据
        original = original_rows[idx] if idx < len(original_rows) else ExcelRow(data={})
        row_dict = dict(original.data)

        # 添加翻译列
        row_dict["Conlang"] = result.conlang
        row_dict["TTS"] = result.tts
        row_dict["Translation_Mode"] = result.mode_used

        if result.unmatched_words:
            row_dict["Unmatched_Words"] = ", ".join(result.unmatched_words)
        else:
            row_dict["Unmatched_Words"] = ""

        if result.error:
            row_dict["Error"] = result.error
        else:
            row_dict["Error"] = ""

        rows_out.append(row_dict)

    df = pd.DataFrame(rows_out)

    try:
        df.to_excel(output_path, index=False, engine="openpyxl")
        return True
    except Exception:
        return False


def export_unmatched_report(
    unmatched_entries: List[UnmatchedWordEntry],
    output_path: str,
) -> bool:
    """导出未匹配词汇报告为 CSV。"""
    try:
        import pandas as pd
    except ImportError:
        # 退化到纯 csv 写入
        try:
            with open(output_path, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(["中文", "自创语", "IPA", "TTS", "构词逻辑",
                                 "创建方式", "创建时间", "AI模型"])
                for entry in unmatched_entries:
                    writer.writerow([
                        entry.chinese, entry.conlang, entry.ipa, entry.tts,
                        entry.logic, entry.created_by, entry.created_time,
                        entry.model,
                    ])
            return True
        except Exception:
            return False

    df_data = []
    for entry in unmatched_entries:
        df_data.append({
            "中文": entry.chinese,
            "自创语": entry.conlang,
            "IPA": entry.ipa,
            "TTS": entry.tts,
            "构词逻辑": entry.logic,
            "创建方式": entry.created_by,
            "创建时间": entry.created_time,
            "AI模型": entry.model,
        })

    df = pd.DataFrame(df_data)
    try:
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
        return True
    except Exception:
        return False