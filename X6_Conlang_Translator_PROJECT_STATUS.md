# Nikki Conlang Forge — 项目状态

## 当前阶段：阶段八（已完成）

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
- **未匹配词汇对话框**（`app/unmatched_words_dialog.py`）：
  - 表格显示所有未匹配词汇（中文 / 自创语 / TTS拼写 / 操作）
  - 每行可手动填写自创语和TTS拼写
  - 单词 AI 生成按钮：调用 PaperHub 为该词生成翻译
  - 全部 AI 生成按钮：批量调用 PaperHub AI 翻译所有未匹配词
  - 全部手动填写 / 跳过 / 保存到词库按钮
- **AI 单词生成 Prompt**：
  - 系统提示词：包含语言白皮书 + 已有词库示例
  - 用户提示词：指定 JSON 格式 `{chinese, conlang, ipa, tts, logic}`
- **批量 AI 生成优化**：多个词汇合并为一个请求，减少 API 调用
- **保存到词库**：
  - 追加到 `Conlang_Master_Library.json`：含 `created_by`、`created_time`、`model` 等富元数据
  - 追加到 `Mapping_Rules.csv`：自创语 + IPA + TTS友好拼写
  - 自动去重（检查词库是否已存在）
- **翻译完成后自动弹出**：有未匹配词汇时自动弹出处理对话框（若 PaperHub 已启用）

### 阶段八（完成）— Excel 台本导入与批量翻译
- **Excel 导入模块**（`app/excel_import.py`）：
  - `ExcelRow(data)` 数据类：保留所有列数据（含额外列），不写死列顺序
  - `ExcelStatistics` 数据类：总行数 / 角色数量 / 角色列表 / 情绪类型数 / 情绪列表
  - `ExcelImportResult(ok, path, rows, columns, missing_columns, statistics, preview_rows, error)` 数据类
  - `read_excel(path)`：读取 .xlsx → 验证必需列（8列：台本ID/Character/Age/Gender/Body_Type/Emotion/Scene_Context/Text） → 计算统计 → 提取前5行预览
  - `get_texts_from_rows(rows)`：提取非空 Text 列值
  - **设计约束**：只验证列存在性，不硬编码列顺序；保留所有额外列在 `ExcelRow.data` 中
- **批量翻译设置对话框**（`app/batch_translate_dialog.py`）：
  - `BatchTranslateSettings` 数据类：mode/rule/hybrid/ai，model，reasoning_enabled，auto_add_new_words，export_unmatched_report，concurrency(3)，request_interval(0.5)
  - `BatchTranslateDialog(QDialog)`：
    - 翻译模式：3 个 QRadioButton（规则翻译/混合翻译/AI翻译）
    - PaperHub AI 设置 QGroupBox（混合/AI模式可见）：
      - 模型下拉框（从 PAPERHUB_MODELS 加载，默认 qwen3-max）
      - ☑ 开启思考模式 / ☑ 自动将新创词汇添加到词库 / ☑ 翻译完成后导出未匹配词汇报告
    - 并发设置：并发请求数 QSpinBox(1-5) / 每次请求间隔 QDoubleSpinBox(0-10s)
    - [开始翻译] / [取消] 按钮
    - API Key 缺失验证（混合/AI模式时检查）
- **批量翻译引擎**（`app/batch_translator.py`）：
  - `BatchTranslateResult` 数据类：row_index/row_id/character/emotion/chinese_text/conlang/tts/mode_used/unmatched_words/new_words/error
  - `BatchTranslateWorker(QThread)`：
    - `progress` 信号：`(row_index, total, BatchTranslateResult)`
    - `finished` 信号：`(results, unmatched_entries, error_msg)`
    - `cancel()` 方法：设置 `_cancelled` 标志
    - 三种翻译模式逻辑：
      - **rule**：纯规则翻译
      - **hybrid**：规则优先 → 未匹配词 AI 补全 → AI 失败则规则回退
      - **ai**：全 AI 翻译 → AI 失败则规则回退
    - `_call_ai_translate(text)`：调用 `translate_with_paperhub(strategy="always")`
    - `_auto_add_new_words(new_words)`：自动写入 master_library JSON + mapping_rules CSV（含富元数据）
    - 请求间隔：`time.sleep(request_interval)` 防限流
    - 空行跳过（mode_used="skip"）
  - `export_results_to_excel(results, original_rows, output_path)`：导出翻译结果 Excel（新增 Conlang/TTS/Translation_Mode/Unmatched_Words/Error 列）
  - `export_unmatched_report(entries, output_path)`：导出未匹配词汇 CSV报告（中文/自创语/IPA/TTS/构词逻辑/创建方式/创建时间/AI模型）
- **主窗口批量功能集成**（`app/main_window.py` 修改）：
  - `_pick_excel()`：选择 Excel → `read_excel()` → 列缺失警告 → 预览对话框（QTableWidget 前5行 + 统计标签） → batch_log 统计文本
  - `_on_batch_start()`：检查 Excel 已导入 → `BatchTranslateDialog` → 构建 bundle（含 master_library_path/mapping_rules_path） → 启动 `BatchTranslateWorker`
  - `_on_batch_progress()`：更新进度条 + batch_log 逐行日志
  - `_on_batch_finished()`：存储结果 + 统计摘要 → 未匹配词弹出 `UnmatchedWordsDialog` → 自动导出未匹配报告（如设置要求） → 刷新资料
  - `_on_batch_export()`：导出翻译结果 Excel
  - `_show_about()`：更新为阶段八文本

---

## 文件结构（当前）

```text
X6_Conlang_Translator/
├─ app/
│  ├─ __init__.py
│  ├─ add_word_dialog.py           ← Phase 4（保留，不再调用）
│  ├─ asset_validation.py          ← Phase 1
│  ├─ batch_translate_dialog.py    ← Phase 8（批量翻译设置对话框）
│  ├─ batch_translator.py          ← Phase 8（批量翻译引擎+导出）
│  ├─ excel_import.py              ← Phase 8（Excel台本导入）
│  ├─ history_writer.py            ← Phase 4
│  ├─ import_classify.py           ← Phase 1
│  ├─ lexicon_segment.py           ← Phase 2
│  ├─ main_window.py               ← Phase 8（批量功能集成+预览+进度）
│  ├─ material_service.py          ← Phase 3
│  ├─ paperhub_client.py           ← Phase 6（完整Prompt+策略+JSON解析）
│  ├─ paperhub_confirm_dialog.py   ← Phase 6（AI建议确认对话框）
│  ├─ paperhub_settings.py         ← Phase 5
│  ├─ paperhub_settings_dialog.py  ← Phase 6
│  ├─ parse_history_json.py        ← Phase 2
│  ├─ parse_lexicon.py             ← Phase 2
│  ├─ parse_mapping_csv.py         ← Phase 2
│  ├─ parse_whitepaper.py          ← Phase 2
│  ├─ rule_translator.py           ← Phase 4
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

1. **`paperhub_client.py` 默认 `max_tokens=4096`**：用户若已有旧配置 `2048` 仍会被读取覆盖——建议后续引导用户更新
2. **`AddWordDialog` 保留但未使用**：`app/add_word_dialog.py` 仍被 main_window.py 导入但不再调用（阶段七的 `UnmatchedWordsDialog` 替代了它的功能）。建议后续清理此导入和文件。
3. **`paperhub_confirm_dialog.py` 有 `\r\n` 行尾**：该文件全文使用 CRLF 行尾，在字符串中出现 `\r\n` 时可能导致 Python 解析问题。建议后续统一为 LF 行尾或修复字符串中的 `\r\n`。
4. **`_whitepaper_full` 默认 `max_chars=3000`**：批量翻译 AI 调用时未显式指定 max_chars，白皮书超过 3000 字符时会被截断。建议后续根据实际白皮书长度调整此参数。

---

## 下一阶段建议（阶段九：TTS 批量生成 / 调优 / UI 美化）

1. **TTS 批量生成**：读取翻译结果 Excel，根据 Character/Age/Gender/Body_Type/Emotion/Scene_Context + TTS拼写，批量调用 TTS API 生成音频文件
2. **批量翻译增强**：
   - 中断续翻（记录翻译进度，下次从断点继续）
   - 翻译结果缓存（避免重复翻译相同文本）
   - 更精细的并发控制（semaphore 替代简单间隔）
3. **UI 美化与体验**：
   - 深色主题 / 自定义主题
   - 翻译结果实时预览（每行翻译完立即显示在表格中）
   - 拖放文件导入
   - 键盘快捷键
4. **代码清理**：
   - 移除 `add_word_dialog.py` 及其导入
   - 统一文件行尾为 LF
   - 添加单元测试

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
- app/material_service.py

当前已完成阶段0到阶段8。
规则翻译 + PaperHub AI 翻译核心 + 未匹配词汇处理 + Excel 台本导入与批量翻译已完整。
现在继续做：……（写你当前的需求）
```