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
from app.ssml_generator import generate_ssml_tag
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
    body_type: str = ""        # Body_Type（体型）
    age: str = ""              # Age（年龄段）
    scene_context: str = ""    # Scene_Context
    chinese_text: str = ""     # Text（原文）
    conlang: str = ""          # 自创语翻译
    tts: str = ""              # TTS 音译
    ssml_tag: str = ""         # SSML 语音标签
    mode_used: str = ""        # 实际使用的翻译模式
    ai_generated: bool = False  # 是否使用 PaperHub AI 生成
    ai_model: str = ""          # AI 模型名（如 "qwen3-max"）
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
      log_message(msg) — 日志消息（用于实时显示）
      finished(results, unmatched_entries, error_msg) — 全部完成

    支持：
      - 暂停/继续（pause/resume）
      - 取消（cancel）
      - AI 请求重试（限流时最多 3 次，指数退避）
      - 请求间隔（避免限流）
      - SSML 标签生成（基于 Emotion / Body_Type / Age）
    """

    progress = pyqtSignal(int, int, object)       # (row_index, total, BatchTranslateResult)
    log_message = pyqtSignal(str)                  # 日志消息
    finished = pyqtSignal(list, list, str)         # (results, unmatched_entries, error_msg)

    # ── 重试常量 ──────────────────────────────────────────────
    _MAX_RETRIES = 3
    _RETRY_BASE_DELAY = 2.0   # 首次重试等待 2 秒，指数递增

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
        self._paused = False

    def cancel(self) -> None:
        """取消翻译。"""
        self._cancelled = True
        self._paused = False  # 取消时解除暂停，让线程能退出

    def pause(self) -> None:
        """暂停翻译（可恢复）。"""
        self._paused = True

    def resume(self) -> None:
        """继续翻译。"""
        self._paused = False

    @property
    def is_paused(self) -> bool:
        return self._paused

    def _wait_if_paused(self) -> None:
        """暂停时阻塞等待，直到恢复或取消。"""
        while self._paused and not self._cancelled:
            time.sleep(0.2)

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

        self.log_message.emit(f"开始批量翻译，共 {total} 行，模式：{self._settings.mode}")

        for idx, row in enumerate(self._rows):
            # ── 检查取消/暂停 ──────────────────────────────────────
            self._wait_if_paused()
            if self._cancelled:
                error_msg = "用户取消了翻译。"
                self.log_message.emit("⚠ 翻译已取消")
                break

            # ── 提取行数据 ──────────────────────────────────────────
            chinese_text = row.data.get("Text", "").strip()
            row_id = row.data.get("台本ID", "")
            character = row.data.get("Character", "")
            emotion = row.data.get("Emotion", "")
            body_type = row.data.get("Body_Type", "") or "Normal"
            age = row.data.get("Age", "") or "Middle"
            scene_context = row.data.get("Scene_Context", "")

            # 日志：正在翻译
            label = row_id or character or f"行{idx + 1}"
            self.log_message.emit(f"正在翻译 [{idx + 1}/{total}] {label}…")

            result = BatchTranslateResult(
                row_index=idx,
                row_id=row_id,
                character=character,
                emotion=emotion,
                body_type=body_type,
                age=age,
                scene_context=scene_context,
                chinese_text=chinese_text,
            )

            if not chinese_text:
                # 空行直接跳过
                result.conlang = ""
                result.tts = ""
                result.ssml_tag = ""
                result.mode_used = "skip"
                results.append(result)
                self.progress.emit(idx, total, result)
                self.log_message.emit(f"  ↳ 空行，跳过")
                continue

            # ── 规则翻译 ──────────────────────────────────────────
            rule_result: Optional[RuleTranslationResult] = None
            try:
                rule_result = translate_multiline_rule(chinese_text, lexicon, tts_map)
            except Exception as exc:
                result.error = f"规则翻译失败：{exc}"
                result.mode_used = "rule_error"
                # 仍然生成空 SSML
                result.ssml_tag = ""
                results.append(result)
                self.progress.emit(idx, total, result)
                self.log_message.emit(f"  ↳ ❌ 规则翻译失败：{exc}")
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
                    # 有未匹配词，调用 AI 补全（带重试）
                    ai_result = self._call_ai_translate(chinese_text)
                    if ai_result and not ai_result.error:
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
                # 全部 AI 翻译（带重试）
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

            # ── 生成 SSML 标签 ────────────────────────────────────
            result.ssml_tag = generate_ssml_tag(
                emotion=result.emotion,
                body_type=result.body_type,
                age=result.age,
                tts_phonetic=result.tts,
            )

            # ── 标记 AI 参与情况 ──────────────────────────────────
            ai_modes = {"hybrid_ai", "ai", "ai_rule_fallback"}
            result.ai_generated = result.mode_used in ai_modes
            if result.ai_generated:
                result.ai_model = self._settings.model

            # ── 日志反馈 ────────────────────────────────────────────
            if result.error:
                self.log_message.emit(f"  ↳ ⚠ {result.mode_used} — {result.error}")
            else:
                unmatched_count = len(result.unmatched_words)
                match_info = f"未匹配词 {unmatched_count}" if unmatched_count else "全覆盖"
                self.log_message.emit(
                    f"  ↳ ✓ {result.mode_used}（{match_info}）"
                )

            # ── 收集未匹配词 ────────────────────────────────────────
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

            # ── 请求间隔（避免限流）─── 暂停感知 ──────────────────
            if mode != "rule" and idx < total - 1:
                interval = self._settings.request_interval
                if interval > 0:
                    # 分段 sleep，以便暂停/取消能及时响应
                    remaining = interval
                    while remaining > 0 and not self._cancelled:
                        self._wait_if_paused()
                        if self._cancelled:
                            break
                        chunk = min(remaining, 0.5)
                        time.sleep(chunk)
                        remaining -= chunk

        # ── 自动添加新词到词库 ────────────────────────────────────
        if self._settings.auto_add_new_words and all_new_words and not self._cancelled:
            self.log_message.emit(f"自动添加 {len(all_new_words)} 个新词到词库…")
            self._auto_add_new_words(all_new_words)

        # ── 汇总失败行 ────────────────────────────────────────────
        failed = [r for r in results if r.error]
        if failed:
            self.log_message.emit(f"⚠ {len(failed)} 行翻译失败，详情见导出文件")
        if not self._cancelled:
            self.log_message.emit(f"✓ 批量翻译完成，成功 {total - len(failed)}/{total} 行")

        self.finished.emit(results, all_unmatched, error_msg)

    def _call_ai_translate(self, text: str) -> Optional[PaperHubResult]:
        """
        调用 PaperHub AI 翻译，带重试机制。

        限流或网络错误时最多重试 _MAX_RETRIES 次，
        每次重试间隔指数递增（2s → 4s → 8s）。
        暂停/取消状态下不发起请求。
        """
        ph_settings = dict(self._paperhub_settings)
        ph_settings["paperhub_strategy"] = "always"  # 批量时用 always 策略
        ph_settings["paperhub_model"] = self._settings.model
        ph_settings["paperhub_reasoning_enabled"] = self._settings.reasoning_enabled

        for attempt in range(1, self._MAX_RETRIES + 1):
            self._wait_if_paused()
            if self._cancelled:
                return PaperHubResult(error="翻译已取消")

            try:
                return translate_with_paperhub(ph_settings, self._bundle, text)
            except PaperHubError as exc:
                # 判断是否为可重试错误：
                #   - 429/503（限流/服务不可用）：可重试
                #   - 无 status_code 的服务器错误：可能可重试
                #   - 4xx 客户端错误（401/403/404等）：不可重试，立即返回
                is_retryable = (
                    exc.status_code in (429, 503)
                    or exc.status_code == 0  # 未知服务器错误，可能可重试
                )
                if is_retryable and attempt < self._MAX_RETRIES:
                    delay = self._RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    self.log_message.emit(
                        f"  ↳ 限流/服务错误({exc.status_code})，第 {attempt}/{self._MAX_RETRIES} 次重试，等待 {delay}s…"
                    )
                    # 暂停感知等待
                    remaining = delay
                    while remaining > 0 and not self._cancelled:
                        self._wait_if_paused()
                        if self._cancelled:
                            return PaperHubResult(error="翻译已取消")
                        chunk = min(remaining, 0.5)
                        time.sleep(chunk)
                        remaining -= chunk
                else:
                    # 不可重试的客户端错误（4xx），或已达最大重试次数
                    return PaperHubResult(error=exc.user_hint or str(exc))
            except Exception as exc:
                if attempt < self._MAX_RETRIES:
                    delay = self._RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    self.log_message.emit(
                        f"  ↳ 网络错误，第 {attempt}/{self._MAX_RETRIES} 次重试，等待 {delay}s…"
                    )
                    remaining = delay
                    while remaining > 0 and not self._cancelled:
                        self._wait_if_paused()
                        if self._cancelled:
                            return PaperHubResult(error="翻译已取消")
                        chunk = min(remaining, 0.5)
                        time.sleep(chunk)
                        remaining -= chunk
                else:
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
                with master_file.open("r", encoding="utf-8-sig") as fh:
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
        except Exception as exc:
            self.log_message.emit(f"❌ 自动入库失败（主词库 {master_file.name}）：{exc}")

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
        except Exception as exc:
            self.log_message.emit(f"❌ 自动入库失败（映射表 {mapping_file.name}）：{exc}")


# --------------------------------------------------------------------------- 
# 导出功能
# --------------------------------------------------------------------------- 

def generate_timestamp_filename(original_path: str) -> str:
    """
    生成带时间戳的输出文件名。

    格式：原文件名_TTS_Ready_时间戳.xlsx
    例如：NPC_Script_TTS_Ready_20250429_143052.xlsx
    """
    stem = Path(original_path).stem if original_path else "Translation"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stem}_TTS_Ready_{timestamp}.xlsx"


def export_results_to_excel(
    results: List[BatchTranslateResult],
    original_rows: List[ExcelRow],
    output_path: str,
) -> Dict[str, Any]:
    """
    将翻译结果导出为 Excel 文件（阶段十规范）。

    新增列：
      Translation_ID   — 翻译记录ID，格式 "TH_序号"
      Conlang_Text     — 自创语文本
      TTS_Phonetic     — TTS 友好音译
      SSML_Tag         — SSML 语音标签
      Unmatched_Words  — 未匹配词汇（如有）
      AI_Generated     — 是否AI生成（Yes/No）
      AI_Model         — AI模型名

    返回导出统计字典：
      {
        "success": bool,
        "total_rows": int,
        "success_count": int,
        "failed_count": int,
        "ai_generated_count": int,
        "new_words_count": int,
        "ai_model": str,
      }
    """
    try:
        import pandas as pd
    except ImportError:
        return {"success": False}

    # 构建导出数据
    rows_out: List[Dict[str, Any]] = []
    for idx, result in enumerate(results):
        # 保留原始列数据
        original = original_rows[idx] if idx < len(original_rows) else ExcelRow(data={})
        row_dict = dict(original.data)

        # ── 阶段十新增列 ─────────────────────────────────────────────
        seq = idx + 1
        row_dict["Translation_ID"] = f"TH_{seq:04d}"
        row_dict["Conlang_Text"] = result.conlang
        row_dict["TTS_Phonetic"] = result.tts
        row_dict["SSML_Tag"] = result.ssml_tag
        row_dict["Unmatched_Words"] = ", ".join(result.unmatched_words) if result.unmatched_words else ""
        row_dict["AI_Generated"] = "Yes" if result.ai_generated else "No"
        row_dict["AI_Model"] = result.ai_model if result.ai_generated else ""

        rows_out.append(row_dict)

    df = pd.DataFrame(rows_out)

    # ── 列顺序：原始列 → 新增列
    original_cols = list(original_rows[0].data.keys()) if original_rows else []
    new_cols = [
        "Translation_ID",
        "Conlang_Text",
        "TTS_Phonetic",
        "SSML_Tag",
        "Unmatched_Words",
        "AI_Generated",
        "AI_Model",
    ]
    # 去重 + 只保留实际存在的列
    all_cols = original_cols + [c for c in new_cols if c not in original_cols]
    all_cols = [c for c in all_cols if c in df.columns]
    df = df[all_cols]

    # ── 统计数据 ─────────────────────────────────────────────────────
    total_rows = len(results)
    success_count = sum(1 for r in results if r.conlang and not r.error)
    failed_count = sum(1 for r in results if r.error)
    ai_generated_count = sum(1 for r in results if r.ai_generated)
    new_words_count = sum(len(r.new_words) for r in results)
    # 取第一个 AI 行的模型名作为代表
    ai_model = ""
    for r in results:
        if r.ai_model:
            ai_model = r.ai_model
            break

    stats = {
        "success": True,
        "total_rows": total_rows,
        "success_count": success_count,
        "failed_count": failed_count,
        "ai_generated_count": ai_generated_count,
        "new_words_count": new_words_count,
        "ai_model": ai_model,
    }

    try:
        df.to_excel(output_path, index=False, engine="openpyxl")
        return stats
    except Exception:
        return {"success": False}


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