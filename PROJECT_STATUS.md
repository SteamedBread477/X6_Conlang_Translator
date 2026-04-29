# Nikki Conlang Forge — 项目状态

## 当前阶段：阶段四（已完成）

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
- 可选 AI 辅助翻译（`app/ai_client.py`）
  - 支持 Claude（Anthropic）和 Gemini（Google）
  - AI 设置对话框（`app/ai_settings_dialog.py`）
  - 仅在词库外词汇存在时调用 AI（节约 API 用量）

### 阶段四（完成）
- **单句翻译核心 — 规则模式三级流水线**：
  1. **第一级：中文 → 自创语**（`app/rule_translator.py`）
     - 预处理：去除多余空格
     - 按标点分句（`。！？，、`），保留标点
     - 词库最长匹配分词
     - 未命中词用 `【词】` 标记，连续未命中字符自动合并
  2. **第二级：自创语 → TTS 友好音译**
     - 逐 token 查 `Mapping_Rules.csv`
     - 已匹配 → TTS 拼写；Level-1 未命中 → 保留 `【词】`
  3. **第三级：翻译历史写入**（`app/history_writer.py`）
     - 追加到 `Translation_History.json`（JSON 数组格式）
     - 记录字段：id、timestamp、source、conlang、phonetic、unmatched_words、emotion 等
- **情绪检测存根**（`detect_emotion()`，预留 TTS 批量生成接口）
  - 基于关键字规则，返回 `EmotionResult`（label / intensity / tts_pitch_hint / tts_rate_hint）
  - 后续可替换为 NLP 模型，接口兼容
- **UI 增强**（`app/main_window.py`）：
  - 三个输出框各配「复制」按钮（中文输入 / 自创语输出 / TTS 音译）
  - 统计栏：匹配率 / 耗时 / 未命中数 / 情绪标签 / AI 辅助标记
  - AI 模式：规则翻译始终先行（提供统计），AI 仅在启用且有未匹配词时补全
  - 未匹配词汇时显示「将未匹配词添加到词库…」按钮
- **未匹配词添加对话框**（`app/add_word_dialog.py`）：
  - 逐词填写自创语翻译 + TTS 拼写
  - 一键写入 `Conlang_Master_Library.json` 与 `Mapping_Rules.csv`
  - 写入后自动刷新内存词库索引

---

## 文件结构（当前）

```text
X6_Conlang_Translator/
├─ app/
│  ├─ __init__.py
│  ├─ add_word_dialog.py        ← Phase 4 新增
│  ├─ ai_client.py
│  ├─ ai_settings_dialog.py
│  ├─ ai_settings_store.py
│  ├─ asset_validation.py
│  ├─ history_writer.py         ← Phase 4 新增
│  ├─ import_classify.py
│  ├─ lexicon_segment.py
│  ├─ main_window.py
│  ├─ material_service.py
│  ├─ parse_history_json.py
│  ├─ parse_lexicon.py
│  ├─ parse_mapping_csv.py
│  ├─ parse_whitepaper.py
│  ├─ rule_translator.py        ← Phase 4 新增
│  ├─ storage.py
│  └─ ui_theme.py
├─ data/
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

## 下一阶段建议（阶段五：批量翻译）

1. 读取 Excel（openpyxl），遍历指定列
2. 对每行调用 `translate_multiline_rule`（+ 可选 AI 补全）
3. 写回翻译结果列
4. 进度条与日志实时更新（QThread 后台执行）
5. 导出结果 Excel

待考虑：
- 批量翻译的错误恢复（中断续翻）
- 情绪字段写入 Excel（为 TTS 批量生成预留）
