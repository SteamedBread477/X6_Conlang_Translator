# Nikki Conlang Forge — 项目状态

## 当前阶段：阶段六（已完成）

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
- **AI 建议确认对话框**（`app/paperhub_confirm_dialog.py`）：
  - 显示自创语文本、TTS 音译（可编辑）
  - 新词建议表格（中文 | 自创语 | TTS 拼写 | 构词逻辑）
  - 三按钮：采用建议 / 修改后采用 / 放弃
- **异步翻译线程**（`_PaperHubTranslateThread`）：
  - QThread 后台执行，不阻塞 UI
  - 翻译时显示进度条，支持取消
  - AI 翻译完成后自动询问是否将新词添加到词库
- **错误处理完善**：
  - `PaperHubError` 异常类（含用户友好提示 `user_hint`）
  - 分类处理：API Key 无效 → 检查设置 / 网络错误 → 检查网络 / 超时 → 进度条 / 响应格式错误 → 手动修正 / 模型错误 → 建议更换
  - 所有策略均支持规则翻译回退
- **新词入库**：
  - AI 翻译产生的 `[NEW]` 新词，翻译完成后弹窗询问添加到词库
  - 确认的新词写入 `Conlang_Master_Library.json`

---

## 文件结构（当前）

```text
X6_Conlang_Translator/
├─ app/
│  ├─ __init__.py
│  ├─ add_word_dialog.py           ← Phase 4
│  ├─ asset_validation.py
│  ├─ history_writer.py            ← Phase 4
│  ├─ import_classify.py
│  ├─ lexicon_segment.py           ← Phase 2
│  ├─ main_window.py               ← Phase 6（异步线程+confirm+新词入库）
│  ├─ material_service.py
│  ├─ paperhub_client.py           ← Phase 6（完整Prompt+策略+JSON解析+错误处理）
│  ├─ paperhub_confirm_dialog.py   ← Phase 6（AI建议确认对话框）
│  ├─ paperhub_settings.py         ← Phase 5
│  ├─ paperhub_settings_dialog.py  ← Phase 6（confirm策略已启用）
│  ├─ parse_history_json.py
│  ├─ parse_lexicon.py
│  ├─ parse_mapping_csv.py
│  ├─ parse_whitepaper.py
│  ├─ rule_translator.py           ← Phase 4
│  ├─ storage.py
│  └─ ui_theme.py
├─ data/
│  ├─ app_config.json              ← Phase 5（PaperHub 配置）
│  ├─ config.json                  ← Phase 0（应用状态）
│  └─ <语言资料夹>/ ...
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
- 阶段六的 `paperhub_client.py` 默认 `max_tokens=4096`，但用户若已有旧配置 `2048` 仍会被读取覆盖——建议后续引导用户更新

## 下一阶段建议（阶段七：批量翻译）

1. 读取 Excel（openpyxl），遍历指定列
2. 对每行调用 `translate_multiline_rule`（+ 可选 PaperHub 补全）
3. 写回翻译结果列
4. 进度条与日志实时更新（QThread 后台执行）
5. 导出结果 Excel
6. 批量翻译的错误恢复（中断续翻）

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

当前已完成阶段0到阶段6。
规则翻译 + PaperHub AI 翻译核心已完整（三种策略 + confirm对话框 + 异步线程 + 新词入库）。
现在继续做：……（写你当前的需求）
```