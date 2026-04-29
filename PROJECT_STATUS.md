# Nikki Conlang Forge — 项目状态

## 当前阶段：阶段九（已完成）

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
- **PaperHub AI 接入模块**（替换原 Claude/Gemini 方案）：
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
- **未匹配词汇对话框**（`app/unmatched_words_dialog.py`）：
  - 表格显示所有未匹配词汇（中文 / 自创语 / TTS拼写 / 操作）
  - 单词 AI 生成 / 全部 AI 生成 / 全部手动填写 / 跳过 / 保存到词库
- **AI 单词生成 Prompt**：白皮书 + 词库示例 → JSON `{chinese, conlang, ipa, tts, logic}`
- **批量 AI 生成优化**：多个词汇合并为一个请求
- **保存到词库**：追加到 `Conlang_Master_Library.json`（含 `created_by/created_time/model`）+ `Mapping_Rules.csv`
- **翻译完成后自动弹出**处理对话框

### 阶段八（完成）— Excel 台本导入与批量翻译
- **Excel 导入模块**（`app/excel_import.py`）：
  - 8 列必需列验证（不写死列顺序，保留额外列）
  - 统计信息：总行数 / 角色数量 / 角色列表 / 情绪类型数
  - 前 5 行预览（QTableWidget 预览对话框）
- **批量翻译设置对话框**（`app/batch_translate_dialog.py`）：
  - 3 翻译模式（规则/混合/AI），模型下拉，3 复选框
  - 并发设置（1-5 并发，0-10s 间隔）
  - API Key 缺失验证
- **批量翻译引擎**（`app/batch_translator.py`）：
  - `BatchTranslateWorker(QThread)`：三种模式逻辑 + AI 回退
  - `_auto_add_new_words`：自动写入词库（含富元数据）
  - 请求间隔防限流
  - `export_results_to_excel`：翻译结果 Excel（新增 Conlang/TTS/Translation_Mode/Unmatched_Words/Error 列）
  - `export_unmatched_report`：未匹配词汇 CSV 报告
- **主窗口集成**：
  - `_pick_excel()`：导入 → 验证 → 预览 → 统计
  - `_on_batch_start()`：设置对话框 → bundle 构建 → 启动 Worker
  - `_on_batch_progress()`：进度条 + 逐行日志
  - `_on_batch_finished()`：结果统计 → 未匹配词对话框 → 报告导出 → 资料刷新
  - `_on_batch_export()`：导出翻译结果 Excel

---

## 文件结构（当前）

```text
X6_Conlang_Translator/
├─ app/
│  ├─ __init__.py
│  ├─ add_word_dialog.py           ← Phase 4（保留，不再调用）
│  ├─ asset_validation.py          ← Phase 1
│  ├─ batch_translate_dialog.py    ← Phase 8
│  ├─ batch_translator.py          ← Phase 8
│  ├─ excel_import.py              ← Phase 8
│  ├─ history_writer.py            ← Phase 4
│  ├─ import_classify.py           ← Phase 1
│  ├─ lexicon_segment.py           ← Phase 2
│  ├─ main_window.py               ← Phase 8（批量功能集成）
│  ├─ material_service.py          ← Phase 3
│  ├─ paperhub_client.py           ← Phase 6
│  ├─ paperhub_confirm_dialog.py   ← Phase 6
│  ├─ paperhub_settings.py         ← Phase 5
│  ├─ paperhub_settings_dialog.py  ← Phase 6
│  ├─ parse_history_json.py        ← Phase 2
│  ├─ parse_lexicon.py             ← Phase 2
│  ├─ parse_mapping_csv.py         ← Phase 2
│  ├─ parse_whitepaper.py          ← Phase 2
│  ├─ rule_translator.py           ← Phase 4
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

1. `paperhub_client.py` 默认 `max_tokens=4096`，旧配置 `2048` 仍会被覆盖
2. `AddWordDialog` 保留但未使用（阶段七 `UnmatchedWordsDialog` 替代）
3. `paperhub_confirm_dialog.py` 有 `\r\n` 行尾，字符串中 `\r\n` 可能导致解析问题
4. `_whitepaper_full` 默认 `max_chars=3000`，批量翻译 AI 调用时可能截断长白皮书

---

## 下一阶段建议（阶段九）

1. TTS 批量生成（读取翻译结果 Excel → 根据 TTS 拼写生成音频）
2. 批量翻译增强（中断续翻 / 翻译缓存 / 精细并发控制）
3. UI 美化（深色主题 / 实时预览 / 拖放导入 / 键盘快捷键）
4. 代码清理（移除 `add_word_dialog.py` / 统一 LF 行尾 / 单元测试）