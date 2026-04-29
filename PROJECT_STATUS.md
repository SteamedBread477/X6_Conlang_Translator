# Nikki Conlang Forge — 项目状态

## 当前阶段：阶段五（已完成）

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
- 可选 AI 辅助翻译（初版，Claude/Gemini，已被阶段五替换）

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
    - `test_paperhub_connection()` — 后台线程测试连接
    - `translate_multiline_paperhub()` — 多行 AI 辅助翻译
    - 支持 reasoning 思考模式（`extra_body: {"reasoning": {"enabled": true}}`）
  - `app/paperhub_settings_dialog.py`：完整设置对话框
    - API Key 输入（密码模式 + 显示/隐藏切换）
    - 服务地址只读显示（`https://tc-paperhub.diezhi.net/v1`）
    - 4 个模型单选按钮（qwen3-max / glm-5 / doubao-seed-2-0-pro / qwen3.5-plus）
    - 3 种 AI 使用策略（仅未匹配 / 全部 / 候选确认[预留]）
    - 高级参数：思考模式 / Temperature / Max Tokens
    - 「测试连接」按钮（QThread 后台，不阻塞 UI）
    - 底部 PaperHub 工作台帮助链接
- **菜单调整**：「工具」→「设置」，入口改为「PaperHub 设置…」
- **翻译流程更新**：规则翻译始终先行；PaperHub AI 根据策略（未匹配/全部）补全
- **requirements.txt**：移除 anthropic / google-generativeai，新增 openai

---

## 文件结构（当前）

```text
X6_Conlang_Translator/
├─ app/
│  ├─ __init__.py
│  ├─ add_word_dialog.py           ← Phase 4
│  ├─ ai_client.py                 （遗留，暂保留）
│  ├─ ai_settings_dialog.py        （遗留，暂保留）
│  ├─ ai_settings_store.py         （遗留，暂保留）
│  ├─ asset_validation.py
│  ├─ history_writer.py            ← Phase 4
│  ├─ import_classify.py
│  ├─ lexicon_segment.py
│  ├─ main_window.py
│  ├─ material_service.py
│  ├─ paperhub_client.py           ← Phase 5
│  ├─ paperhub_settings.py         ← Phase 5
│  ├─ paperhub_settings_dialog.py  ← Phase 5
│  ├─ parse_history_json.py
│  ├─ parse_lexicon.py
│  ├─ parse_mapping_csv.py
│  ├─ parse_whitepaper.py
│  ├─ rule_translator.py           ← Phase 4
│  ├─ storage.py
│  └─ ui_theme.py
├─ data/
│  ├─ app_config.json              ← Phase 5（PaperHub 配置）
│  ├─ config.json
│  └─ <语言资料夹>/
│     ├─ Conlang_Master_Library.json
│     ├─ Mapping_Rules.csv
│     ├─ Translation_History.json
│     ├─ whitepaper.md
│     └─ derived/material_snapshot.json
├─ main.py
├─ PROJECT_STATUS.md
├─ README.md
└─ requirements.txt
```

---

## 下一阶段建议（阶段六：批量翻译）

1. 读取 Excel（openpyxl），遍历指定列
2. 对每行调用 `translate_multiline_rule`（+ 可选 PaperHub 补全）
3. 写回翻译结果列
4. 进度条与日志实时更新（QThread 后台执行）
5. 导出结果 Excel

待考虑：
- 批量翻译的错误恢复（中断续翻）
- 情绪字段写入 Excel（为 TTS 批量生成预留）
