# Nikki Conlang Forge 开发日志

> 项目全称：Nikki Conlang Forge（无限暖暖自创语翻译器）
> 技术栈：Python 3.9 + PyQt5 + OpenAI SDK + Pandas + OpenPyXL
> 仓库：https://github.com/SteamedBread477/X6_Conlang_Translator
> 文档更新日期：2026-05-01

---

## 项目起源

Nikki Conlang Forge 诞生于一个具体需求：为游戏《无限暖暖》中的虚构语言（如帕克索尔语、菇菇语）提供从中文到自创语的翻译工具链。项目从零开始构建，经历了 12 个开发阶段，从一个基础骨架成长为具备完整翻译管线、AI 集成和主题系统的桌面应用。

---

## 阶段回顾

### 阶段零 — 项目骨架（✅ 已完成）

**目标**：建立可运行的 PyQt5 主窗口和基础数据结构。

- 项目目录结构搭建（`app/` 包 + `data/` 数据目录）
- PyQt5 主窗口框架，支持多语言页签的添加与重命名
- 基于 JSON 的应用状态存储（`data/config.json`）
- 单句翻译区与批量翻译区的界面预留
- 四种语言资料文件的导入入口（白皮书/词库/映射规则/翻译历史）
- `app/app_paths.py` 和 `app/storage.py` 作为底层工具

**关键文件**：`main.py`, `app/main_window.py`, `app/storage.py`, `app/app_paths.py`

---

### 阶段一 — 资料校验与类型识别（✅ 已完成）

**目标**：确保用户导入的资料文件格式正确，并能自动识别类型。

- 四种资料文件的严格校验规则（`app/asset_validation.py`）
  - 白皮书：Markdown 格式 + 必含 `# 语法` / `# 词法` 等章节
  - 词库：JSON 格式 + 必含 `{中文: 自创语}` 映射
  - 映射规则：CSV 格式 + 必含 `自创语` / `TTS音译` 列
  - 翻译历史：JSON 格式 + 必含翻译记录数组
- 文件导入时的类型自动识别（`app/import_classify.py`），根据文件扩展名和内容特征判断
- 左侧面板的资料状态实时显示（✓ 已导入 / ○ 未导入 / ✗ 格式错误）

**关键文件**：`app/asset_validation.py`, `app/import_classify.py`

---

### 阶段二 — 解析器矩阵与词库分词（✅ 已完成）

**目标**：将四种资料文件解析为可计算的结构化数据。

- 四个解析器的完整实现：
  - `app/parse_lexicon.py`：JSON 词库 → `{中文: 自创语}` 双向索引
  - `app/parse_mapping_csv.py`：Mapping_Rules.csv → `{自创语: TTS}` 映射字典
  - `app/parse_whitepaper.py`：Markdown 白皮书 → 结构化语法规则（词法/句法/音系）
  - `app/parse_history_json.py`：翻译历史 → 锚点字典（已知翻译对）
- Material Bundle 快照机制（`derived/material_snapshot.json`），导入后自动生成
- 词库段切分器（`app/lexicon_segment.py`）：最长匹配算法，将中文句子切分为词库已知片段 + 未匹配片段

**关键文件**：`app/parse_lexicon.py`, `app/parse_mapping_csv.py`, `app/parse_whitepaper.py`, `app/parse_history_json.py`, `app/lexicon_segment.py`

---

### 阶段三 — 资料导入流水线与语言包管理（✅ 已完成）

**目标**：串联校验→识别→解析为完整流水线，并支持语言包的导出/导入。

- 完整资料导入与解析流水线（`app/material_service.py`）
- 语言包 ZIP 导出/导入（将整个语言资料夹打包为 `.zip`）
- 语言删除、右键菜单、语言备注功能
- 导入失败时的友好错误提示

**关键文件**：`app/material_service.py`

---

### 阶段四 — 规则翻译引擎（✅ 已完成）

**目标**：实现从中文到自创语的核心翻译逻辑。

- **三级流水线翻译架构**（`app/rule_translator.py`）：
  1. **中文 → 自创语**：词库最长匹配，未命中部分用 `【词】` 标记
  2. **自创语 → TTS 音译**：逐 token 查 Mapping_Rules.csv，生成 TTS 友好读音
  3. **翻译历史写入**（`app/history_writer.py`），JSON 数组格式持久化
- 情绪检测存根（`detect_emotion()`），预留后续 TTS 批量生成接口
- UI 增强：三输出框（自创语/TTS/SSML）各加「复制」按钮、统计栏（匹配率/耗时/未命中数/情绪）

**关键文件**：`app/rule_translator.py`, `app/history_writer.py`

---

### 阶段五 — PaperHub AI 平台接入（✅ 已完成）

**目标**：接入 PaperHub AI 平台，为翻译提供智能辅助。

- `app/paperhub_settings.py`：配置存取模块，写入 `data/app_config.json`
- `app/paperhub_client.py`：OpenAI SDK 兼容客户端，支持 PaperHub API 调用
- `app/paperhub_settings_dialog.py`：完整设置对话框（API Key / 模型选择 / 端点配置）
- 菜单入口：「工具」→「设置」→「PaperHub 设置…」
- 替换了早期基于 Claude/Gemini 的 `ai_client.py` 架构

**关键文件**：`app/paperhub_settings.py`, `app/paperhub_client.py`, `app/paperhub_settings_dialog.py`

**架构决策**：选择 PaperHub 作为 AI 后端而非直接使用 Claude/Gemini，因为 PaperHub 提供了统一的模型路由接口（qwen3-max / glm-5 / doubao-seed-2-0-pro / qwen3.5-plus 等），避免了多 API Key 的管理复杂度。

---

### 阶段六 — PaperHub AI 翻译核心（✅ 已完成）

**目标**：让 AI 真正参与翻译流程，而非仅作为配置存根。

- **翻译 Prompt 升级**：白皮书全文 + 词库 + 翻译历史锚定，JSON 输出格式
- **三种翻译策略**：
  - `unmatched_only`：先规则翻译，仅词库外片段交给 AI 补全
  - `always`：整句由 AI 翻译，参考词库保持一致性
  - `confirm`：AI 生成候选翻译，弹出对话框让用户确认或修改
- **AI 建议确认对话框**（`app/paperhub_confirm_dialog.py`）
- **异步翻译线程**：QThread 后台执行，不阻塞 UI
- **错误处理体系**：`PaperHubError` 异常类 + 分类处理（网络/认证/限流）+ 规则回退
- **新词入库**：AI 翻译新词弹窗询问 → 确认后写入词库

**关键文件**：`app/paperhub_client.py`, `app/paperhub_confirm_dialog.py`

---

### 阶段七 — 未匹配词汇 AI 处理（✅ 已完成）

**目标**：为规则翻译无法覆盖的词汇提供多种处理方式。

- **未匹配词汇对话框**（`app/unmatched_words_dialog.py`）
- 四种处理策略：
  - 单词 AI 生成：逐词调用 PaperHub 获取自创语翻译
  - 全部 AI 生成：批量调用 AI 生成所有未匹配词
  - 全部手动填写：用户自行输入自创语对应词
  - 跳过：保留 `【词】` 标记不做处理
- 保存到词库功能：追加到 `Conlang_Master_Library.json` + `Mapping_Rules.csv`

**关键文件**：`app/unmatched_words_dialog.py`

---

### 阶段八 — Excel 台本批量翻译（✅ 已完成）

**目标**：支持从 Excel 台本文件导入并批量翻译，面向游戏配音制作场景。

- Excel 导入模块（8列验证 + 统计 + 预览）→ `app/excel_import.py`
- 批量翻译设置对话框（3模式 + 并发设置）→ `app/batch_translate_dialog.py`
- 批量翻译引擎（Worker + 三模式 + 导出）→ `app/batch_translator.py`
- 台本标准列结构：台本ID / Character / Age / Gender / Body_Type / Emotion / Scene_Context / Text

**关键文件**：`app/excel_import.py`, `app/batch_translate_dialog.py`, `app/batch_translator.py`

---

### 阶段九 — SSML 语音标签 + 重试 + 暂停控制（✅ 已完成）

**目标**：为翻译结果生成 TTS 可用的 SSML 标签，并增强批量翻译的健壮性。

- **SSML 语音标签生成模块**（`app/ssml_generator.py`）：
  - 7 种情绪映射（Sad/Happy/Urgent/Calm/Angry/Fear/Neutral）
  - Body_Type 体型 pitch 叠加（Normal/Strong/Heavy）
  - Age 年龄 rate 微调
- 批量翻译暂停/继续/取消控制
- AI 请求限流重试（指数退避，retryable: 429/503/连接超时）

**关键文件**：`app/ssml_generator.py`

**设计决策**：SSML 标签基于 W3C 标准 `<prosody>` 元素，叠加计算公式为 Emotion 基线 + Body_Type pitch 增量 + Age rate 增量，确保不同角色特征产生差异化语音表现。

---

### 阶段十 — 导出增强与历史同步（✅ 已完成）

**目标**：完善导出流程，实现翻译结果与历史记录的自动同步。

- **时间戳命名导出**（`generate_timestamp_filename`）：避免导出文件名冲突
- **导出统计对话框**（`app/export_result_dialog.py`）：展示翻译完成率、AI 使用率、未匹配统计
- **新创词汇报告对话框**（`app/new_words_report_dialog.py`）：列出本次翻译中 AI 生成的新词
- **导出 Excel 列名标准化**：Translation_ID / Conlang_Text / TTS_Phonetic / SSML_Tag / Unmatched_Words / AI_Generated / AI_Model
- **翻译结果自动同步到 Translation_History.json**
- **AI 生成追踪**：`BatchTranslateResult.ai_generated` + `ai_model` 字段

**关键文件**：`app/export_result_dialog.py`, `app/new_words_report_dialog.py`

---

### 阶段十一 — UI 主题系统（✅ 已完成）

**目标**：将所有硬编码样式抽象为可配置的 Theme Token 系统，支持多皮肤切换。

- **Theme Token 抽象层**（`app/ui_theme.py`，905 行）：
  - `ThemeTokens` 数据类：颜色、字体、圆角、阴影、间距、背景等全部设计变量
  - `MacaronPurpleTheme`：默认主题（极简 SaaS 风马卡龙紫配色）
  - `ThemeManager` 单例：主题注册、切换、QSS 生成、全局应用
  - QSS 生成基于 `setProperty("class", ...)` + `setObjectName` 双注解，regex 自动复写
  - `token()` / `inline_style()` 便捷方法供对话框动态状态颜色使用
- **AppearanceDialog 外观设置对话框**（`app/appearance_dialog.py`）：主题选择下拉框 + 预览 + Apply/Close
- **主窗口重构**（`app/main_window.py`）：15 个组件使用语义注解，移除所有硬编码 `setStyleSheet`
- **对话框重构**：6 个对话框的硬编码样式全部改用 `theme_manager.token()` / `inline_style()`

**关键文件**：`app/ui_theme.py`, `app/appearance_dialog.py`, `app/main_window.py`

**架构决策**：选择 Token 抽象而非简单 CSS 变量，因为 PyQt5 的 QSS 不支持原生 CSS 变量语法。Token 系统确保换肤时只需定义新的 `ThemeTokens` 实例，所有组件样式自动跟随。

---

### 阶段十一补充 — 4K 高 DPI 适配（✅ 已完成）

**目标**：确保应用在 Windows 4K/175% DPI 缩放环境下界面元素大小舒适。

- 全局启用 `Qt.AA_EnableHighDpiScaling` + `Qt.AA_UseHighDpiPixmaps`（`main.py`）
- ThemeTokens 尺寸 token 全面上调：

| Token 类别 | 变量 | 原值 | 新值 |
|-----------|------|------|------|
| 字号 | font_size_sm | 12 | 13 |
| 字号 | font_size_md | 14 | 15 |
| 字号 | font_size_lg | 16 | 18 |
| 字号 | font_size_xl | 18 | 20 |
| 字号 | font_size_heading | 24 | 28 |
| 按钮/控件 | btn_height_sm | 28 | 34 |
| 按钮/控件 | btn_height_md | 36 | 44 |
| 按钮/控件 | btn_height_lg | 44 | 54 |
| 按钮/控件 | input_height | 60 | 80 |
| 按钮/控件 | sidebar_width | 220 | 280 |
| QSS | checkbox/radiobutton indicator | 18px | 22px |
| QSS | progressbar | 18px | 24px |

**原理**：Qt 的 `AA_EnableHighDpiScaling` 让 widget 布局按 OS DPI 比率（约 175%）自动放大，而 QSS 中的 px 字号是物理像素不受缩放影响，因此同步上调字号 token 确保文字在 4K 屏上足够大。

---

### 阶段十一后维护 — 构建修复与数据格式诊断

**时间**：2026-05-01

#### 构建修复

- `build.bat`：移除已删除的测试文件引用（test_stage9.py, test_stage10.py），步骤编号从 [1/4]-[4/4] 更新为 [1/3]-[3/3]
- `build.spec`：新增 `app.appearance_dialog` 到 `hiddenimports` 列表（遗漏导致打包后外观对话框无法打开）
- PyInstaller 构建成功 → `dist/X6_Conlang_Translator.exe`（~68MB，2026/5/1 16:49）
  - 注意：PowerShell 将 stderr INFO 日志误判为错误导致 exit code 1，但构建实际成功

#### 数据格式兼容性问题诊断

**发现**：用户的帕克索尔语资料文件（`dist/data/帕克索尔语/`）使用学术嵌套格式，与应用解析器期望的扁平格式不兼容。项目根 `data/帕克索尔语/` 仍为空占位符。

**详细分析**：

1. **Conlang_Master_Library.json**：使用嵌套格式 `{language_info, vocabulary: [{root, part_of_speech, paxor_spelling, chinese_meaning, ipa_phonetic, derivatives, usage_context}]}`，约 60 条。解析器期望 `{"中文词": "自创语词"}` 或含 ZH_KEYS/CON_KEYS 的对象。`chinese_meaning` 和 `paxor_spelling` 不在识别集合中 → 0 词提取。

2. **Mapping_Rules.csv**：列头 `"帕克索尔语字母"` 不匹配解析器关键词（自创语词汇/自创语/词汇/词形）→ ValueError。CSV 同时包含字母级行（A a, E e, P p... 占位 "sul"）和词级行（sul→sul, gom?→goh-mah, zakil→thah-keel 等）。

3. **Translation_History.json**：复杂嵌套文档，包含 `core_concepts_anchoring`（用 `paxor_word`/`chinese_translation`）和 `fixed_expressions_anchoring`（用 `paxor_expression`/`chinese_translation`）。这些键不在 ZH_KEYS 或 CON_KEYS 中 → 0 锚点提取。

4. **whitepaper.md**：项目根为一行占位符，`dist/data/` 中为完整 12 节 ~2000 行学术文档（种族生理建模/音系学推导/声调系统/音节结构/拼写系统/语法拓扑/构词法/词汇体系/语言文化生态/示范语料/TTS引擎适配建议/附录）。

**解析器识别集合**（精确）：
- ZH_KEYS：`zh, cn, chinese, 中文, source, src, han, hanzi, 原文, 汉语`
- CON_KEYS：`conlang, target, tl, translation, 译, 译本, 译词, 词, 词条, 自创语, 目标语`
- CSV 列关键词：自创语词汇/自创语/词汇/词形（word 列）、TTS/tts/友好拼写/拼写（TTS 列）、IPA/ipa/音标（IPA 列）

**修复方案**（待执行）：
- 方案 A：将 3 个用户文件转换为应用兼容的扁平格式（快速修复）
- 方案 B：增强解析器以识别更多键名变体（长期健壮性）

---

## 当前应用架构总览

```
┌─────────────────────────────────────────────────────────┐
│                    MainWindow (PyQt5)                    │
│  ┌──────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │ 语言管理  │  │  单句翻译区       │  │ 批量翻译区   │  │
│  │ 页签/导入 │  │ 规则→AI→未匹配词 │  │ Excel→导出   │  │
│  └──────────┘  └──────────────────┘  └──────────────┘  │
├─────────────────────────────────────────────────────────┤
│                    服务层 (app/)                          │
│  ┌────────────┐ ┌──────────┐ ┌───────────┐             │
│  │ Material   │ │ Rule     │ │ PaperHub  │             │
│  │ Service    │ │ Translator│ │ Client    │             │
│  └────────────┘ └──────────┘ └───────────┘             │
│  ┌────────────┐ ┌──────────┐ ┌───────────┐             │
│  │ SSML       │ │ Batch    │ │ History   │             │
│  │ Generator  │ │ Translator│ │ Writer    │             │
│  └────────────┘ └──────────┘ └───────────┘             │
├─────────────────────────────────────────────────────────┤
│                    UI 主题层                              │
│  ┌────────────┐ ┌──────────┐ ┌───────────┐             │
│  │ Theme      │ │ Theme    │ │ Appearance│             │
│  │ Tokens     │ │ Manager  │ │ Dialog    │             │
│  └────────────┘ └──────────┘ └───────────┘             │
├─────────────────────────────────────────────────────────┤
│                    数据层 (data/)                         │
│  config.json │ app_config.json │ languages/<语言>/       │
│  白皮书.md │ 词库.json │ 映射.csv │ 历史.json           │
└─────────────────────────────────────────────────────────┘
```

---

## 已删除的废弃资产

| 文件 | 删除时间 | 原因 |
|------|---------|------|
| `app/ai_client.py` | 阶段六 | 被 `paperhub_client.py` 替代 |
| `app/ai_settings_dialog.py` | 阶段六 | 被 `paperhub_settings_dialog.py` 替代 |
| `app/ai_settings_store.py` | 阶段六 | 被 `paperhub_settings.py` 替代 |
| `data/app_state.json` | 阶段六 | 迁移至 `data/config.json` |
| `get-pip.py` | 阶段六 | pip 临时安装文件 |
| `X6_Conlang_Translator_PROJECT_STATUS.md` | 阶段十一 | 与 `PROJECT_STATUS.md` 重复 |
| `test_stage9.py` | 阶段十一 | 旧测试文件，已被后续 pytest 覆盖 |
| `build_debug.spec` | 阶段十一 | debug 构建配置冗余 |

---

## 当前已知问题

1. **Translation_ID 不一致**：Excel 导出用 `TH_{idx+1:04d}`（位置序号），`append_translation_record` 用 `TH_{n:04d}`（基于已有记录数）
2. **NewWordsReportDialog._add_to_lexicon 标志未被消费**：按钮设置标志但 ExportResultDialog 不获取
3. **paperhub_confirm_dialog.py CRLF 行尾**：全文 `\r\n` 行尾，应统一为 LF
4. **_whitepaper_full max_chars=3000**：批量翻译 AI 调用时可能截断长白皮书（帕克索尔语完整白皮书 ~2000 行）
5. **os.startfile Windows-specific**：ExportResultDialog 的"打开文件夹/打开文件"按钮仅 Windows 可用
6. **线程安全**：`_paused`/`_cancelled` bool 标志无互斥锁保护
7. **数据格式兼容性**：帕克索尔语用户资料文件使用学术嵌套格式，与应用解析器期望的扁平格式不兼容（详见阶段十一后维护段）

---

## 后续开发待办

以下待办按优先级排列，包含用户直接需求与对照「X6_语音生成工作流预研_蒸汽面包」文档的迭代方向。

### 🔴 P0 — 用户直接需求（阶段十二核心）

#### 待办 1：App 主图标定版

- **现状**：应用目前使用系统默认图标，无品牌辨识度
- **目标**：
  - 设计或选定应用专属图标（建议融入自创语文字元素或紫色品牌色）
  - 图标格式：`.ico`（Windows）+ `.png`（多尺寸 16/32/48/256px）
  - 在 `main.py` 中通过 `app.setWindowIcon()` 设置
  - 在 `build.spec` 中配置 PyInstaller 图标嵌入
  - 任务栏图标 + 窗口标题栏图标同步

#### 待办 2：界面设计主要风格定版（浅色/深色）

- **现状**：Theme Token 系统已支持多皮肤，但只有 MacaronPurple（浅色）一套主题
- **目标**：
  - 设计一套完整的 **深色主题**（DarkMode），Token 定义包括：
    - 深色背景系列：bg → #1E1E2E, sidebar → 深紫, card → #2A2A3C
    - 高对比文字：text → #E0E0E0, muted → #888
    - 调整圆角/阴影适配深色氛围
  - 在 `ui_theme.py` 中新增 `DarkModeTheme` 类
  - AppearanceDialog 中增加深色选项，切换即时生效
  - 确保所有对话框在深色模式下控件可读、按钮可辨识
  - 考虑跟随系统深色模式自动切换（Windows Dark Mode Detection）

#### 待办 3：新增翻译后 AI 朗读按钮

- **现状**：翻译结果只有文本输出，无法即时听到发音效果
- **目标**：
  - 在单句翻译区的三个输出框旁各加一个「朗读」按钮（🔊 图标）
  - 朗读引擎选项：
    - **系统 TTS**（Windows SAPI）：零配置即时可用，质量一般
    - **PaperHub TTS API**（如支持）：高质量但需 API 调用
    - **ElevenLabs / Resemble AI**：最佳质量，需 API Key 配置（后续阶段接入）
  - 朗读内容：
    - 自创语框：朗读 Conlang_Text（系统 TTS 可能无法准确发音）
    - TTS 音译框：朗读 TTS_Phonetic（系统 TTS 可较准确发音）
    - SSML 框：朗读带 SSML 标签的文本（需 SSML 解析引擎）
  - 新增 `app/tts_player.py` 模块，封装朗读逻辑
  - 配置项：朗读引擎选择 + 语速 + 音量

#### 待办 4：新增应用程序字体可选项

- **现状**：ThemeTokens 中 `font_family` 硬编码为 `"Microsoft YaHei"`，用户无法自定义
- **目标**：
  - 在 AppearanceDialog 中新增「字体选择」下拉框
  - 使用 `QFontDatabase.families()` 读取用户系统已安装的所有字体
  - 字体选择实时预览（在对话框中展示当前字体的效果文本）
  - 选定字体后更新 `ThemeTokens.font_family` 并重新应用主题
  - 字体偏好持久化到 `data/app_config.json`
  - 启动时读取已保存字体偏好，覆盖默认 Token
  - 注意：自创语可能需要特殊字体（如 Unicode 扩展区字符），建议允许为「自创语输出框」单独设置字体

---

### 🟡 P1 — SSML 标签增强（对照文档阶段三深化）

#### 待办 5：`<phoneme>` 标签支持

- **现状**：`ssml_generator.py` 只生成 `<prosody>` 标签，TTS_Phonetic 列产出音译文本但不包裹 `<phoneme>`
- **目标**：
  - 在 `generate_ssml_tag()` 中增加 `phoneme_mode` 参数
  - 自动生成 `<phoneme alphabet="ipa" ph="kə-tæk">K'tak</phoneme>` 格式
  - Resemble AI 的核心优势就是 `<phoneme>` 标签精准发音，此功能为后续 Resemble 接入做准备
  - Mapping_Rules.csv 中增加 `ipa_phoneme` 列存储 IPA 音标

#### 待办 6：`<break>` 标签支持

- **现状**：无词间停顿控制
- **目标**：
  - 在 Mapping_Rules.csv 中增加 `break_after` 列（单位 ms）
  - 根据自创语词长自动插入合理停顿（短词 50ms, 长词 100ms）
  - SSML 输出增加 `<break time="100ms"/>` 标签

#### 待办 7：ElevenLabs voice_settings 映射

- **现状**：SSML 是 W3C 标准，ElevenLabs 实际用 JSON 参数 `voice_settings` 控制情绪
- **目标**：
  - 新增 `app/voice_settings_mapper.py`
  - 将 Emotion → stability / similarity_boost / style_exaggeration 三参数映射
  - 输出格式适配 ElevenLabs API 的 `voice_settings` JSON 字段

---

### 🟡 P2 — 数据结构对齐文档标准

#### 待办 8：Gender 字段补全

- **现状**：`ExcelRow` 和 `BatchTranslateResult` 缺少 `gender` 字段
- **目标**：
  - 新增 Gender 字段（Male/Female/Neutral）
  - Gender 用于后续 Voice ID 匹配和 SSML pitch 基线调整
  - 文档强调 Gender 决定基础音色区间，是语音生成的必要参数

#### 待办 9：Phonetic_Script 列独立化

- **现状**：当前 `tts` 字段实际是音译层，命名与文档标准不一致
- **目标**：
  - 将 `tts` 字段重命名为 `phonetic_script`，与文档术语对齐
  - 导出 Excel 列名同步更新

#### 待办 9½：数据格式兼容性修复

- **现状**：帕克索尔语用户资料使用学术嵌套格式，解析器无法识别
- **目标**：
  - 增强解析器识别集合，新增 `chinese_meaning`, `paxor_spelling`, `paxor_word`, `paxor_expression`, `帕克索尔语字母` 等变体
  - 或提供格式转换工具，将学术格式一键转为应用兼容格式
  - 同步更新项目根 `data/帕克索尔语/` 占位文件与 `dist/data/帕克索尔语/` 实际文件

---

### 🟢 P3 — 语音生成管线接入（对照文档阶段五）

#### 待办 10：ElevenLabs API 模块

- 新增 `app/elevenlabs_client.py`
  - 读取批量翻译结果的 TTS_Phonetic + SSML_Tag + Emotion 列
  - Emotion → `voice_settings` 动态映射
  - 支持 Voice ID 映射表（Character → Voice ID 配置文件）
  - 输出 `.wav` 音频文件，命名格式 `{ID}_{Character}_{Emotion}.wav`
  - API 限流控制（rate limit + 指数退避重试）

#### 待办 11：Resemble AI API 模块

- 新增 `app/resemble_client.py`
  - 支持自创语言（IPA `<phoneme>` 标签 + SSML `<prosody>` + `<emotion>`）
  - Phonetic_Script → `<phoneme alphabet="ipa" ph="...">` 自动包裹
  - Body_Type Heavy → `<prosody pitch="-10%">` 自动叠加
  - 按量计费追踪（$0.006/秒）

#### 待办 12：音色映射管理

- 新增 `app/voice_mapping.py` + 配置界面
  - Character → Voice ID / Voice UUID 映射表（JSON 格式）
  - Age / Gender / Body_Type → 音色推荐逻辑
  - 音色试听功能（单句生成预览）

#### 待办 13：冒烟测试（预检生成）流程

- 批量语音生成前，每个角色抽取 1-2 句先验证
  - 检查语速、情绪、发音准确度
  - 提供修正反馈入口（如文本末尾加 `!!!` 强制提高语调）

---

### 🟢 P4 — RVC 后处理管线

#### 待办 14：RVC 声音转换接口

- 新增 `app/rvc_client.py`
  - 输入：ElevenLabs/Resemble 生成的干声 `.wav`
  - 调用本地 RVC-WebUI 的 CLI/API
  - 参数：Index Rate + Pitch 调整
  - 输出：最终种族音色 `.wav`
  - 初期只做接口定义 + 配置界面，实际 RVC 部署由用户自行完成

---

### 🟢 P5 — 批量流程优化

#### 待办 15：中断续翻

- 当前批量翻译中断后无法续翻
- 持久化中间进度（JSON checkpoint），重启后可从断点继续

#### 待办 16：翻译缓存

- 相同文本不重复调用 AI
- 基于 `(chinese_text, mode)` 做 LRU 缓存，减少 API 费用和等待时间

#### 待办 17：并发精细控制

- 当前 `BatchTranslateSettings` 的并发参数较粗糙
- 文档建议 `time.sleep(0.5)` 限流，应更精细地控制不同 API 的速率
- 分层限流：ElevenLabs 3 req/s, Resemble 5 req/s, PaperHub 按用户配置

---

### 🔵 P6 — 代码质量与工程规范

#### 待办 18：统一 LF 行尾

- 全项目文件统一为 LF 行尾（`.gitattributes` + editorconfig）

#### 待办 19：Translation_ID 对齐

- 修复 Excel 导出与 `append_translation_record` 的 ID 生成逻辑不一致问题

#### 待办 20：线程安全加固

- `_paused` / `_cancelled` 标志加互斥锁保护（`threading.Lock`）

#### 待办 21：新词入库标志消费

- 修复 `NewWordsReportDialog._add_to_lexicon` 标志未被 `ExportResultDialog` 消费的 bug

---

## 阶段规划

| 阶段 | 内容 | 优先级 | 对应文档阶段 |
|------|------|--------|------------|
| **阶段十二** | App 主图标定版 + 深色主题设计定版 + 翻译后 AI 朗读按钮 + 系统字体可选项 | P0 | UI 持续改进 |
| **阶段十三** | SSML 增强：`<phoneme>` + `<break>` + voice_settings 映射 + Gender 字段 + 数据格式兼容性修复 | P1-P2 | 阶段三深化 |
| **阶段十四** | ElevenLabs + Resemble AI 语音生成模块 + 音色映射管理 + 冒烟测试流程 | P3 | 阶段五 |
| **阶段十五** | RVC 后处理接口 + 批量流程优化（续翻/缓存/限流） | P4-P5 | 阶段五补充 |
| **阶段十六** | 代码质量：LF 行尾 / Translation_ID / 线程安全 / 标志消费 | P6 | 工程规范 |

---

## 文档对照：X6_语音生成工作流预研

应用与「语音生成工作流预研_蒸汽面包」文档的阶段对照：

| 文档阶段 | 应用对应模块 | 覆盖度 |
|----------|-------------|--------|
| 阶段一：语言学底层构建 | 白皮书解析 + PaperHub AI | ✅ 已覆盖 |
| 阶段二：持久化词库与规范化 | 词库/映射/历史三大资产 + 新词入库 | ✅ 已覆盖 |
| 阶段三：智能翻译器 | 规则翻译 + AI翻译 + SSML标签 | ✅ 已覆盖（待深化） |
| 阶段四：台词库生成 | Excel 台本导入 + 批量翻译 + 导出 | ✅ 已覆盖 |
| 阶段五：批量语音生产 | ❌ 未覆盖 | — |

**核心缺口**：应用目前止步于"文本资产生产"，文档后半段（语音生成管线）完全未接入。阶段十四将填补此缺口。

---

## 续聊入口（新会话时发给 AI）

```text
请继续开发 H:\QvQ_X6\X6_Tools\X6_Conlang_Translator（Nikki Conlang Forge，无限暖暖自创语翻译器）。
GitHub 仓库：https://github.com/SteamedBread477/X6_Conlang_Translator

请先阅读以下文件：
- DEVLOG.md（开发日志与完整待办清单）
- PROJECT_STATUS.md
- README.md
- app/ui_theme.py
- app/main_window.py

当前已完成阶段0到11（含4K DPI适配）+ 构建修复 + 数据格式兼容性诊断。
规则翻译 + PaperHub AI 翻译 + SSML 语音标签 + 批量翻译 + 导出增强 + 主题 Token 系统已完成。
已知问题：7项（详见 DEVLOG.md 已知问题段）。
现在继续做：……（写你当前的需求）
```