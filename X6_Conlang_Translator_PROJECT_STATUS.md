# Nikki Conlang Forge — 项目状态

## 当前阶段：阶段十（已完成）

---

## 已完成阶段

### 阶段零（完成）
- 项目基础目录结构
- 可运行的 PyQt5 主窗口
- 多语言页签的添加与重命名
- 基于 JSON 的应用状态存储（`data/config.json`）
- 单句翻译区与批量翻译区的界面预留
- 四种语言资料文件的导入入口

### 阶段一（完成）
- 四种资料文件的严格校验规则（`app/asset_validation.py`）
- 文件导入时的类型自动识别（`app/import_classify.py`）
- 左侧面板的资料状态实时显示（✓ / ○ / ✗）

### 阶段二（完成）
- 基础解析器完整实现：
  - `app/parse_lexicon.py`：JSON 词库 → `{中文: 自创语}` 索引
  - `app/parse_mapping_csv.py`：Mapping_Rules.csv → `{自创语: TTS}` 映射
  - `app/parse_whitepaper.py`：Markdown 白皮书 → 结构化语法规则
  - `app/parse_history_json.py`：翻译历史 → 锚点字典
- Material Bundle 快照（`derived/material_snapshot.json`）
- 词库段切分器（`app/lexicon_segment.py`，最长匹配算法）

### 阶段三（完成）
- 完整资料导入与解析流水线（`app/material_service.py`）
- 语言包 ZIP 导出/导入
- 语言删除、右键菜单
- 语言备注功能

### 阶段四（完成）
- **单句翻译核心 — 规则模式三级流水线**（`app/rule_translator.py`）：
  1. 中文 → 自创语：词库最长匹配，未命中用 `【词】` 标记
  2. 自创语 → TTS 友好音译：逐 token 查 Mapping_Rules.csv
  3. 翻译历史写入（`app/history_writer.py`），JSON 数组格式
- 情绪检测存根（`detect_emotion()`），预留 TTS 批量生成接口
- UI 增强：三输出框各加「复制」按钮、统计栏（匹配率/耗时/未命中数/情绪）
- 未匹配词添加对话框（`app/add_word_dialog.py`）

### 阶段五（完成）
- **PaperHub AI 接入模块**（初版）：
  - `app/paperhub_settings.py`：配置存取，写入 `data/app_config.json`
  - `app/paperhub_client.py`：OpenAI SDK 兼容客户端（两行文本输出格式）
  - `app/paperhub_settings_dialog.py`：设置对话框
  - 菜单调整：「工具」→「设置」→「PaperHub 设置…」

### 阶段六（完成）— PaperHub AI 翻译核心
- **翻译 Prompt 升级**：
  - 系统提示词：包含语言白皮书全文 + 词库 + 翻译历史锚定
  - 用户提示词：指定 JSON 输出格式 `{conlang_text, new_words[], tts_phonetic}`
  - 新词标注 `[NEW]`，确保词库一致性
- **三种翻译策略**：
  - `unmatched_only`：先规则翻译，未匹配词汇调用 AI 补全
  - `always`：整句直接 AI 翻译（参考词库保持一致性）
  - `confirm`：AI 生成候选 → 弹出确认对话框 → 用户采用/修改/放弃
- **AI 建议确认对话框**（`app/paperhub_confirm_dialog.py`）
- **异步翻译线程**（`_PaperHubTranslateThread`）：QThread 后台执行，不阻塞 UI
- **错误处理完善**：`PaperHubError` 异常类 + 分类处理 + 规则回退
- **新词入库**：AI 翻译新词弹窗询问 → 确认写入 `Conlang_Master_Library.json`

### 阶段七（完成）— 未匹配词汇处理（AI辅助）
- **未匹配词汇对话框**（`app/unmatched_words_dialog.py`）
- AI 单词生成 / 全部 AI 生成 / 全部手动填写 / 跳过 / 保存到词库
- 保存到词库：追加到 `Conlang_Master_Library.json`（含富元数据）+ `Mapping_Rules.csv`

### 阶段八（完成）— Excel 台本导入与批量翻译
- **Excel 导入模块**（`app/excel_import.py`）：
  - 8 列必需列验证 + 统计 + 前5行预览
  - `ExcelRow(data)` / `ExcelStatistics` / `ExcelImportResult` 数据类
- **批量翻译设置对话框**（`app/batch_translate_dialog.py`）：
  - 3 翻译模式 / 模型下拉 / 并发设置
- **批量翻译引擎**（`app/batch_translator.py`）：
  - `BatchTranslateWorker(QThread)` 三种模式 + AI回退
  - `export_results_to_excel` + `export_unmatched_report`
- **主窗口集成**：导入 → 预览 → 翻译 → 导出完整流程

### 阶段九（完成）— SSML 语音标签 + 重试 + 暂停/取消
- **SSML 语音标签生成模块**（`app/ssml_generator.py`）：
  - `EMOTION_MAP`：7种情绪 → (rate, pitch, volume) 映射
  - `BODY_TYPE_PITCH`：体型 pitch 调整叠加（Normal/Strong/Heavy → 0/-5%/−10%）
  - `AGE_RATE_ADJUST`：9种年龄×速度组合 → rate 微调映射
  - `_parse_pct` / `_format_pct` / `_add_pcts`：百分比代数运算
  - `ProsodyAttrs` 数据类 + `compute_prosody_attrs()` + `generate_ssml_tag()`
- **BatchTranslateResult 增强**：`ssml_tag` / `body_type` / `age` 字段
- **Worker 核心逻辑升级**：
  - `log_message` 信号：实时日志
  - `pause()` / `resume()` / `cancel()` + `_wait_if_paused()`
  - `_call_ai_translate()` 重试机制：3次指数退避，retryable: 429/503/0
  - `PaperHubError.status_code` 属性
- **S9 bug fixes**：
  1. `rate="medium"` no-op：不写入 `<prosody>`，除非配对 pitch/volume
  2. `Path("")` fallback → `Path.home()/Documents`
  3. `_show_about` 更新为阶段九
  4. `_call_ai_translate` retryable 判断修复：4xx 非限流错误不重试

### 阶段十（完成）— 导出增强与历史同步

- **时间戳命名导出**（`generate_timestamp_filename`，`app/batch_translator.py`）：
  - 格式：`{stem}_TTS_Ready_{YYYYMMDD_HHMMSS}.xlsx`
  - 例：`NPC_Script_TTS_Ready_20250429_143052.xlsx`
  - 空/无路径时回退 stem 为 "Translation"
- **导出统计对话框**（`app/export_result_dialog.py`，阶段十新增）：
  - 标题："✓ 文件已保存"（绿色 16px 粗体）
  - 路径显示（灰色 #555，自动换行）
  - 统计块：总行数/成功/失败/AI生成/新增词汇/模型（背景 #f5f5f5）
  - 四按钮：[查看新创词汇] [打开文件夹] [打开文件] [关闭]
  - "查看新创词汇"：lazy-import `NewWordsReportDialog`，传 `new_words` + `ai_model`
  - "打开文件夹/打开文件"：`os.startfile()`（Windows-specific）
- **新创词汇报告对话框**（`app/new_words_report_dialog.py`，阶段十新增）：
  - 标题："本次翻译共创造 N 个新词汇："
  - QTableWidget 4列（中文/自创语/TTS拼写/构词逻辑），stretch，只读
  - AI来源说明："※ 所有新创词汇均由 PaperHub AI（{model}）生成"
  - 三按钮：[导出词汇表] [全部添加到词库] [关闭]
  - "导出词汇表"：CSV（utf-8-sig，5列含AI模型）
  - "全部添加到词库"：设置 `_added_to_lexicon=True` 标志
  - `get_added_to_lexicon()` 公开方法

- **导出 Excel 列名更新**（S10）：
  - 列顺序：原始列 → Translation_ID → Conlang_Text → TTS_Phonetic → SSML_Tag → Unmatched_Words → AI_Generated → AI_Model
  - Translation_ID：`TH_{seq:04d}`（位置序号）
  - AI_Generated："Yes" / "No" 字符串
  - AI_Model：模型名或空字符串
  - 移除旧列：Translation_Mode / Error
  - 去重逻辑：`original_cols + [c for c in new_cols if c not in original_cols]`，`[c for c in all_cols if c in df.columns]`

- **导出返回 stats dict**（S10）：
  - `export_results_to_excel` 返回 `{success, total_rows, success_count, failed_count, ai_generated_count, new_words_count, ai_model}`
  - `ai_model` 取第一个 AI 行的模型名作为代表
  - 失败时返回 `{success: False}`

- **BatchTranslateResult S10 增强**：
  - 新增 `ai_generated: bool = False`：`mode_used in {"hybrid_ai", "ai", "ai_rule_fallback"}` 时为 True
  - 新增 `ai_model: str = ""`：AI 行的模型名

- **翻译结果自动同步到 Translation_History.json**（`_append_results_to_history`）：
  - 遍历所有 BatchTranslateResult 行，跳过 `not r.conlang` 的行
  - 对每行成功翻译调用 `append_translation_record`
  - 参数：source, conlang, phonetic, unmatched_words, source/target language, mode, emotion, hints

- **主窗口 S10 方法更新**（`app/main_window.py`）：
  - `_do_auto_export(results)`：导出完成后自动流程（时间戳命名 → stats dict → ExportResultDialog）
  - `_on_batch_finished` 重写：先处理未匹配词 → 自动导出（仅 `results and not error_msg`）
  - `_on_batch_export` 重写：使用时间戳命名 + stats dict + ExportResultDialog + 历史同步
  - `_show_about` 更新为阶段十

- **CRLF f-string 修复**：
  - `export_result_dialog.py` 和 `new_words_report_dialog.py` 的多行字符串改用 `"\n".join()` 避免字面 `\r\n`

---

## 文件结构（当前）

```text
X6_Conlang_Translator/
├─ app/
│  ├─ __init__.py
│  ├─ add_word_dialog.py           ← Phase 4（保留，不再调用）
│  ├─ asset_validation.py          ← Phase 1
│  ├─ batch_translate_dialog.py    ← Phase 8（批量翻译设置对话框）
│  ├─ batch_translator.py          ← Phase 8→10（引擎+导出+时间戳命名+stats dict）
│  ├─ excel_import.py              ← Phase 8（Excel台本导入）
│  ├─ export_result_dialog.py      ← Phase 10 NEW（导出完成对话框）
│  ├─ history_writer.py            ← Phase 4
│  ├─ import_classify.py           ← Phase 1
│  ├─ lexicon_segment.py           ← Phase 2
│  ├─ main_window.py               ← Phase 10（S10全部集成）
│  ├─ material_service.py          ← Phase 3
│  ├─ new_words_report_dialog.py   ← Phase 10 NEW（新创词汇报告对话框）
│  ├─ paperhub_client.py           ← Phase 6→9（status_code增强+NewWord类）
│  ├─ paperhub_confirm_dialog.py   ← Phase 6（AI建议确认对话框，⚠ CRLF行尾）
│  ├─ paperhub_settings.py         ← Phase 5
│  ├─ paperhub_settings_dialog.py  ← Phase 6
│  ├─ parse_history_json.py        ← Phase 2
│  ├─ parse_lexicon.py             ← Phase 2
│  ├─ parse_mapping_csv.py         ← Phase 2
│  ├─ parse_whitepaper.py          ← Phase 2
│  ├─ rule_translator.py           ← Phase 4
│  ├─ ssml_generator.py            ← Phase 9（SSML语音标签+rate="medium" no-op fix）
│  ├─ storage.py                   ← Phase 0
│  ├─ unmatched_words_dialog.py    ← Phase 7（未匹配词汇处理对话框）
│  └─ ui_theme.py
├─ data/
│  ├─ app_config.json              ← Phase 5（PaperHub 配置）
│  ├─ config.json                  ← Phase 0（应用状态）
│  └─ languages/
│     └─ <语言资料夹>/
│        ├─ Conlang_Master_Library.json
│        ├─ Mapping_Rules.csv
│        ├─ Translation_History.json
│        ├─ whitepaper.md
│        └─ derived/material_snapshot.json
├─ venv/                           ← Python 虚拟环境
├─ main.py
├─ PROJECT_STATUS.md
├─ README.md
├─ requirements.txt
├─ test_stage9.py
├─ test_stage10.py
└─ X6_Conlang_Translator_PROJECT_STATUS.md
```

---

## 已删除的废弃资产（阶段六清理）

| 文件 | 原因 |
|------|------|
| `app/ai_client.py` | 遗留 Claude/Gemini 客户端，已被 `paperhub_client.py` 完全替代 |
| `app/ai_settings_dialog.py` | 遗留 AI 设置对话框，已被 `paperhub_settings_dialog.py` 替代 |
| `app/ai_settings_store.py` | 遗留 AI 配置存取，已被 `paperhub_settings.py` 替代 |
| `data/app_state.json` | 遗留旧格式状态文件，已迁移至 `data/config.json` |
| `get-pip.py` | pip 引导临时文件，不应纳入版本库 |
| `app/__pycache__/` | Python 编译缓存，不应纳入版本库 |

---

## 当前已知问题

1. **Translation_ID 不一致**：Excel 导出用 `TH_{idx+1:04d}`（位置序号），`append_translation_record` 用 `TH_{n:04d}`（基于已有记录数），同一行在 Excel 和 History JSON 中 ID 不同。这是已知设计权衡——Excel ID 是位置性的，History ID 是持久性/唯一性的。
2. **`NewWordsReportDialog._add_to_lexicon` 标志未被消费**：按钮设置 `_added_to_lexicon=True` 但 ExportResultDialog 不从子对话框获取该标志。实际词库写入由 Worker 的 `_auto_add_new_words` 或手动触发处理。
3. **`AddWordDialog` 保留但未使用**：`app/add_word_dialog.py` 仍被 main_window.py 导入但不再调用（阶段七 `UnmatchedWordsDialog` 替代）
4. **`paperhub_confirm_dialog.py` CRLF 行尾**：全文 `\r\n` 行尾，字符串中 `\r\n` 可能导致解析问题
5. **`_whitepaper_full` max_chars=3000**：批量翻译 AI 调用时可能截断长白皮书
6. **`os.startfile` Windows-specific**：ExportResultDialog 的"打开文件夹/打开文件"按钮
7. **线程安全**：`_paused`/`_cancelled` bool 标志无互斥锁保护（PyQt5实践中风险低）
8. **`_do_auto_export` silent skip**：`_excel_import_result is None or not ok` 时无反馈静默跳过

---

## 下一阶段建议（阶段十一）

1. **TTS 批量音频生成**：读取 SSML_Tag 列批量调用 TTS API 生成音频文件
2. **批量翻译增强**：中断续翻 / 翻译缓存 / 精细并发控制
3. **UI 美化与体验**：深色主题 / 实时预览 / 拖放导入 / 键盘快捷键
4. **代码清理**：移除 `add_word_dialog.py` 及导入 / 统一 LF 行尾 / Translation_ID 对齐

---

## 续聊入口（新会话时发给 AI）

```text
请继续开发 H:\QvQ_X6\X6_Tools\X6_Conlang_Translator（Nikki Conlang Forge，无限暖暖自创语翻译器）。
GitHub 仓库：https://github.com/SteamedBread477/X6_Conlang_Translator

请先阅读以下文件：
- X6_Conlang_Translator_PROJECT_STATUS.md
- README.md
- app/main_window.py
- app/paperhub_client.py
- app/batch_translator.py

当前已完成阶段0到阶段10。
规则翻译 + PaperHub AI 翻译 + SSML 语音标签 + 批量翻译（暂停/取消/重试） + 导出增强（时间戳命名+统计对话框+新创词汇报告+历史同步+AI追踪）已完整。
现在继续做：……（写你当前的需求）
```