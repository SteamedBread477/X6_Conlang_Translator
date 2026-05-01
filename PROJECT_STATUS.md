# Nikki Conlang Forge — 项目状态

## 当前阶段：阶段十一（UI 主题系统）

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

### 阶段十（完成）— 导出增强与历史同步

- **时间戳命名导出**（`generate_timestamp_filename`）
- **导出统计对话框**（`app/export_result_dialog.py`）
- **新创词汇报告对话框**（`app/new_words_report_dialog.py`）
- **导出 Excel 列名更新**：Translation_ID / Conlang_Text / TTS_Phonetic / SSML_Tag / Unmatched_Words / AI_Generated / AI_Model
- **翻译结果自动同步到 Translation_History.json**
- **AI 生成追踪**：`BatchTranslateResult.ai_generated` + `ai_model` 字段

### 阶段十一（进行中）— UI 主题系统

- **Theme Token 抽象层**（`app/ui_theme.py`）：
  - `ThemeTokens` 数据类：颜色、字体、圆角、阴影、间距、背景等所有设计变量
  - `MacaronPurpleTheme`：默认主题实例（极简 SaaS 风马卡龙配色）
  - `ThemeManager` 单例：主题注册、切换、QSS 生成、应用
  - QSS 生成：基于 `setProperty("class", ...)` + `setObjectName` 双注解，regex 自动复写
  - `token()` / `inline_style()` 便捷方法：供对话框动态状态颜色使用
- **AppearanceDialog 外观设置对话框**（`app/appearance_dialog.py`）：
  - 主题选择下拉框 + 预览
  - Apply / Close 按钮
  - 菜单入口：「工具」→「外观…」
- **主窗口重构**（`app/main_window.py`）：
  - 所有硬编码 `setStyleSheet` 已移除
  - 15 个组件使用 `setProperty("class", ...)` + `setObjectName` 语义注解
  - 启动时调用 `theme_manager.apply(app)` + `UITheme.sync_from_manager()`
- **对话框重构**：
  - `paperhub_settings_dialog.py`：动态状态颜色改用 `theme_manager.token()`
  - `paperhub_confirm_dialog.py`：硬编码样式改用 `inline_style()` / `setProperty`
  - `export_result_dialog.py`：硬编码样式改用 `theme_manager`
  - `new_words_report_dialog.py`：硬编码样式改用 `theme_manager`
  - `unmatched_words_dialog.py`：硬编码样式改用 `theme_manager`

---

## 文件结构（当前）

```text
X6_Conlang_Translator/
├─ app/
│  ├─ __init__.py
│  ├─ appearance_dialog.py         ← Phase 11（外观设置对话框）
│  ├─ app_paths.py                 ← Phase 0（路径工具）
│  ├─ asset_validation.py          ← Phase 1
│  ├─ batch_translate_dialog.py    ← Phase 8
│  ├─ batch_translator.py          ← Phase 8→10
│  ├─ excel_import.py              ← Phase 8
│  ├─ export_result_dialog.py      ← Phase 10→11
│  ├─ history_writer.py            ← Phase 4
│  ├─ import_classify.py           ← Phase 1
│  ├─ lexicon_segment.py           ← Phase 2
│  ├─ main_window.py               ← Phase 11（主题注解重构）
│  ├─ material_service.py          ← Phase 3
│  ├─ new_words_report_dialog.py   ← Phase 10→11
│  ├─ paperhub_client.py           ← Phase 6→9
│  ├─ paperhub_confirm_dialog.py   ← Phase 6→11
│  ├─ paperhub_settings.py         ← Phase 5
│  ├─ paperhub_settings_dialog.py  ← Phase 6→11
│  ├─ parse_history_json.py        ← Phase 2
│  ├─ parse_lexicon.py             ← Phase 2
│  ├─ parse_mapping_csv.py         ← Phase 2
│  ├─ parse_whitepaper.py          ← Phase 2
│  ├─ rule_translator.py           ← Phase 4
│  ├─ ssml_generator.py            ← Phase 9
│  ├─ storage.py                   ← Phase 0
│  ├─ unmatched_words_dialog.py    ← Phase 7→11
│  └─ ui_theme.py                  ← Phase 11 NEW（主题 Token 系统）
├─ data/
│  ├─ config.json                  ← Phase 0（应用状态）
│  └─ languages/<语言资料夹>/ ...
├─ main.py
├─ PROJECT_STATUS.md               ← 项目状态（唯一权威文件）
├─ README.md
├─ README.txt                      ← 用户使用说明
├─ requirements.txt
├─ build.spec                      ← PyInstaller 构建配置
├─ build.bat                       ← 构建脚本
└─ 启动.bat                        ← 开发模式启动脚本
```

---

## 已删除的废弃资产


| 文件                                        | 删除时间 | 原因                                  |
| ----------------------------------------- | ---- | ----------------------------------- |
| `app/ai_client.py`                        | 阶段六  | 已被 `paperhub_client.py` 替代          |
| `app/ai_settings_dialog.py`               | 阶段六  | 已被 `paperhub_settings_dialog.py` 替代 |
| `app/ai_settings_store.py`                | 阶段六  | 已被 `paperhub_settings.py` 替代        |
| `data/app_state.json`                     | 阶段六  | 已迁移至 `data/config.json`             |
| `get-pip.py`                              | 阶段六  | pip 临时文件                            |
| `X6_Conlang_Translator_PROJECT_STATUS.md` | 阶段十一 | 与 `PROJECT_STATUS.md` 重复，保留后者       |
| `test_stage9.py`                          | 阶段十一 | 旧阶段测试文件，非 pytest 标准，已被后续测试覆盖        |
| `build_debug.spec`                        | 阶段十一 | debug 构建配置冗余，`build.spec` 已足够       |


---

## 当前已知问题

1. **Translation_ID 不一致**：Excel 导出用 `TH_{idx+1:04d}`（位置序号），`append_translation_record` 用 `TH_{n:04d}`（基于已有记录数）
2. `**NewWordsReportDialog._add_to_lexicon` 标志未被消费**：按钮设置标志但 ExportResultDialog 不获取
3. `**paperhub_confirm_dialog.py` CRLF 行尾**：全文 `\r\n` 行尾
4. `**_whitepaper_full` max_chars=3000**：批量翻译 AI 调用时可能截断长白皮书
5. `**os.startfile` Windows-specific**：ExportResultDialog 的"打开文件夹/打开文件"按钮
6. **线程安全**：`_paused`/`_cancelled` bool 标志无互斥锁保护

---

## 皮肤可配置项清单

以下视觉属性已全部抽象为 Theme Tokens，替换皮肤时只需定义新的 `ThemeTokens` 实例：


| Token 类别 | 具体变量                                                                                        | 默认值（Macaron Purple）                                                                            |
| -------- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| **颜色**   | primary, secondary, highlight, bg, text, stroke, muted, status_ok, status_fail, status_warn | #B39DDB / #BFF629 / #F4FF81 / #FFFFFF / #2D2D2D / #2D2D2D / #999 / #7FCB7F / #E74C3C / #F5A623 |
| **字体**   | font_family, font_size_sm, font_size_md, font_size_lg, font_size_xl, font_size_heading      | "Microsoft YaHei" / 12 / 14 / 16 / 18 / 24                                                     |
| **圆角**   | radius_sm, radius_md, radius_lg                                                             | 4 / 8 / 12                                                                                     |
| **阴影**   | shadow_card, shadow_popup                                                                   | "0 2px 8px rgba(0,0,0,0.08)" / "0 4px 12px rgba(0,0,0,0.15)"                                   |
| **间距**   | spacing_xs, spacing_sm, spacing_md, spacing_lg, spacing_xl                                  | 4 / 8 / 12 / 16 / 24                                                                           |
| **背景**   | sidebar_bg, lang_selector_bg, assets_panel_bg, input_bg, card_bg                            | #B39DDB / #BFF629 / rgba(179,157,219,0.3) / #FFFFFF / #FFFFFF                                  |
| **按钮**   | btn_primary_bg, btn_primary_text, btn_highlight_bg, btn_highlight_text, btn_small_radius    | #B39DDB / #2D2D2D / #F4FF81 / #2D2D2D / 6                                                      |


---

## 下一阶段建议（阶段十二）

1. **新增皮肤**：深色主题 / 磨砂玻璃主题 / 更多配色方案
2. **TTS 批量音频生成**：读取 SSML_Tag 列批量调用 TTS API
3. **批量翻译增强**：中断续翻 / 翻译缓存 / 精细并发控制
4. **代码清理**：统一 LF 行尾 / Translation_ID 对齐

---

## 续聊入口（新会话时发给 AI）

```text
请继续开发 H:\QvQ_X6\X6_Tools\X6_Conlang_Translator（Nikki Conlang Forge，无限暖暖自创语翻译器）。
GitHub 仓库：https://github.com/SteamedBread477/X6_Conlang_Translator

请先阅读以下文件：
- PROJECT_STATUS.md
- README.md
- app/ui_theme.py
- app/main_window.py
- app/appearance_dialog.py

当前已完成阶段0到10，阶段11（UI主题系统）进行中。
规则翻译 + PaperHub AI 翻译 + SSML 语音标签 + 批量翻译 + 导出增强 + 主题 Token 系统 + AppearanceDialog 已完成。
现在继续做：……（写你当前的需求）
```

