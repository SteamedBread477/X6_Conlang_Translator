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
- **PaperHub AI 接入模块**：
  - `app/paperhub_settings.py`：配置存取，写入 `data/app_config.json`
  - `app/paperhub_client.py`：OpenAI SDK 兼容客户端
  - `app/paperhub_settings_dialog.py`：完整设置对话框
  - 菜单调整：「工具」→「设置」→「PaperHub 设置…」

### 阶段六（完成）— PaperHub AI 翻译核心
- **翻译 Prompt 升级**：白皮书全文 + 词库 + 翻译历史锚定，JSON 输出格式
- **三种翻译策略**：unmatched_only / always / confirm
- **AI 建议确认对话框**（`app/paperhub_confirm_dialog.py`）
- **异步翻译线程**（QThread 后台执行，不阻塞 UI）
- **错误处理完善**：`PaperHubError` 异常类 + 分类处理 + 规则回退
- **新词入库**：AI 翻译新词弹窗询问 → 确认写入词库

### 阶段七（完成）— 未匹配词汇处理（AI辅助）
- **未匹配词汇对话框**（`app/unmatched_words_dialog.py`）
- AI 单词生成 / 全部 AI 生成 / 全部手动填写 / 跳过 / 保存到词库
- 保存到词库：追加到 `Conlang_Master_Library.json` + `Mapping_Rules.csv`

### 阶段八（完成）— Excel 台本导入与批量翻译
- Excel 导入模块（8列验证+统计+预览）
- 批量翻译设置对话框（3模式+并发设置）
- 批量翻译引擎（Worker + 三模式 + 导出）

### 阶段九（完成）— SSML 语音标签 + 重试 + 暂停/取消
- SSML 语音标签生成模块（7情绪映射+体型pitch叠加+年龄rate微调）
- 批量翻译暂停/继续/取消控制
- AI请求限流重试（指数退避，retryable: 429/503/0）
- S9 bug fixes: rate="medium" no-op, Path("") fallback, status_code retryable

### 阶段十（完成）— 导出增强与历史同步
- **时间戳命名导出**（`generate_timestamp_filename`）：`NPC_Script_TTS_Ready_20250429_143052.xlsx`
- **导出统计对话框**（`app/export_result_dialog.py`）：成功/失败/AI生成/新创词汇统计 + 查看新创词汇/打开文件夹/打开文件按钮
- **新创词汇报告对话框**（`app/new_words_report_dialog.py`）：表格展示 + 导出CSV + 全部添加到词库标记
- **导出 Excel 列名更新**：Translation_ID / Conlang_Text / TTS_Phonetic / SSML_Tag / Unmatched_Words / AI_Generated / AI_Model（移除旧 Translation_Mode 和 Error 列）
- **翻译结果自动同步到 Translation_History.json**（`_append_results_to_history`）：每行成功翻译自动追加历史记录
- **AI 生成追踪**：`BatchTranslateResult.ai_generated` + `ai_model` 字段，Excel 中 AI_Generated="Yes"/"No" + AI_Model 列
- **导出返回 stats dict**：`export_results_to_excel` 返回 `{success, total_rows, success_count, failed_count, ai_generated_count, new_words_count, ai_model}`
- **手动导出按钮 S10 更新**：`_on_batch_export` 使用时间戳命名 + stats dict + ExportResultDialog + 历史同步
- **CRLF f-string 修复**：`export_result_dialog.py` 和 `new_words_report_dialog.py` 的多行字符串改用 `"\n".join()` 避免字面 `\r\n`

---

## 文件结构（当前）

```text
X6_Conlang_Translator/
├─ app/
│  ├─ __init__.py
│  ├─ add_word_dialog.py           ← Phase 4（保留，不再调用）
│  ├─ asset_validation.py          ← Phase 1
│  ├─ batch_translate_dialog.py    ← Phase 8
│  ├─ batch_translator.py          ← Phase 8→10（引擎+导出+时间戳命名）
│  ├─ excel_import.py              ← Phase 8
│  ├─ export_result_dialog.py      ← Phase 10 NEW（导出完成对话框）
│  ├─ history_writer.py            ← Phase 4
│  ├─ import_classify.py           ← Phase 1
│  ├─ lexicon_segment.py           ← Phase 2
│  ├─ main_window.py               ← Phase 10（S10全部集成）
│  ├─ material_service.py          ← Phase 3
│  ├─ new_words_report_dialog.py   ← Phase 10 NEW（新创词汇报告对话框）
│  ├─ paperhub_client.py           ← Phase 6→9（status_code增强）
│  ├─ paperhub_confirm_dialog.py   ← Phase 6
│  ├─ paperhub_settings.py         ← Phase 5
│  ├─ paperhub_settings_dialog.py  ← Phase 6
│  ├─ parse_history_json.py        ← Phase 2
│  ├─ parse_lexicon.py             ← Phase 2
│  ├─ parse_mapping_csv.py         ← Phase 2
│  ├─ parse_whitepaper.py          ← Phase 2
│  ├─ rule_translator.py           ← Phase 4
│  ├─ ssml_generator.py            ← Phase 9（SSML语音标签）
│  ├─ storage.py                   ← Phase 0
│  ├─ unmatched_words_dialog.py    ← Phase 7
│  └─ ui_theme.py
├─ data/
│  ├─ app_config.json              ← Phase 5（PaperHub 配置）
│  ├─ config.json                  ← Phase 0（应用状态）
│  └─ languages/<语言资料夹>/ ...
├─ venv/
├─ main.py
├─ PROJECT_STATUS.md
├─ README.md
├─ requirements.txt
├─ test_stage9.py
├─ test_stage10.py
└─ X6_Conlang_Translator_PROJECT_STATUS.md
```

---

## 已删除的废弃资产

| 文件 | 原因 |
|------|------|
| `app/ai_client.py` | 已被 `paperhub_client.py` 替代 |
| `app/ai_settings_dialog.py` | 已被 `paperhub_settings_dialog.py` 替代 |
| `app/ai_settings_store.py` | 已被 `paperhub_settings.py` 替代 |
| `data/app_state.json` | 已迁移至 `data/config.json` |
| `get-pip.py` | pip 临时文件 |

---

## 当前已知问题

1. **Translation_ID 不一致**：Excel 导出用 `TH_{idx+1:04d}`（位置序号），`append_translation_record` 用 `TH_{n:04d}`（基于已有记录数），同一行在 Excel 和 History JSON 中 ID 不同
2. **`NewWordsReportDialog._add_to_lexicon` 标志未被消费**：按钮设置 `_added_to_lexicon=True` 但 ExportResultDialog 不从子对话框获取该标志
3. **`AddWordDialog` 保留但未使用**：`app/add_word_dialog.py` 仍被导入但不调用
4. **`paperhub_confirm_dialog.py` CRLF 行尾**：全文 `\r\n` 行尾
5. **`_whitepaper_full` max_chars=3000**：批量翻译 AI 调用时可能截断长白皮书
6. **`os.startfile` Windows-specific**：ExportResultDialog 的"打开文件夹/打开文件"按钮
7. **线程安全**：`_paused`/`_cancelled` bool 标志无互斥锁保护

---

## 下一阶段建议（阶段十一）

1. **TTS 批量音频生成**：读取 SSML_Tag 列批量调用 TTS API
2. **批量翻译增强**：中断续翻 / 翻译缓存 / 精细并发控制
3. **UI 美化**：深色主题 / 实时预览 / 拖放导入 / 键盘快捷键
4. **代码清理**：移除 `add_word_dialog.py` / 统一 LF 行尾 / Translation_ID 对齐

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