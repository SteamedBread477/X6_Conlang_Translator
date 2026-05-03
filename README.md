# Nikki Conlang Forge

`Nikki Conlang Forge`（无限暖暖自创语翻译器）是一个使用 Python + PyQt5 构建的桌面自创语翻译器，支持规则翻译、PaperHub AI 辅助翻译、语言大师多轮对话、Excel 台本批量翻译、4K 高 DPI 适配与可切换主题系统。

## 功能概览

- 多语言页签管理（添加、重命名、删除、备注、图标）
- 四种语言资料文件导入（白皮书 / 词库 / 映射规则 / 翻译历史）
- 规则翻译引擎（词库最长匹配 → TTS 音译 → 翻译历史记录）
- PaperHub AI 辅助翻译（三种策略：仅未匹配 / 全部 / 候选确认）
- AI 新词建议与词库入库
- 未匹配词汇 AI 处理对话框（手动填写 / 单词AI / 批量AI / 保存到词库）
- 语言大师问答（多轮对话式语言创作助手 + 新词候选审核）
- 快捷提问模板（预设 + 自定义管理 + 持久化）
- Excel 台本批量翻译（导入→预览→统计→设置→翻译→导出）
- 批量翻译设置（规则/混合/AI模式、模型选择、并发控制、自动添加新词）
- SSML 语音标签生成（7情绪映射 + 体型pitch叠加 + 年龄rate微调）
- 翻译结果导出为 Excel + 未匹配词汇报告 CSV + 新创词汇报告
- 语言包 ZIP 导出/导入
- UI 主题 Token 系统（马卡龙紫默认 + 可切换皮肤）
- 外观设置对话框（主题选择 + 字体族/缩放偏好 + 持久化）
- 语言图标选择（assets/lang_icons 目录 + 右键菜单选图标）
- 4K 高 DPI 适配

## 项目结构

```text
X6_Conlang_Translator/
├─ app/
│  ├─ __init__.py
│  ├─ app_paths.py                 ← 路径工具（data/assets/lang_icons/ 统一管理）
│  ├─ appearance_dialog.py         ← 外观设置对话框（主题+字体）
│  ├─ asset_validation.py          ← 资料文件校验
│  ├─ batch_translate_dialog.py    ← 批量翻译设置对话框
│  ├─ batch_translator.py          ← 批量翻译引擎+导出
│  ├─ excel_import.py              ← Excel台本导入+验证+统计+预览
│  ├─ export_result_dialog.py      ← 导出统计对话框
│  ├─ font_settings.py             ← 字体偏好配置存取（app_config.json）
│  ├─ history_writer.py            ← 翻译历史写入
│  ├─ import_classify.py           ← 文件类型自动识别
│  ├─ ipa_generator.py             ← IPA 音标生成
│  ├─ lexicon_segment.py           ← 词库最长匹配分词
│  ├─ main_window.py               ← 主窗口（翻译+批量+AI+未匹配词+语言大师问答）
│  ├─ material_service.py          ← 资料导入/解析流水线
│  ├─ new_words_report_dialog.py   ← 新创词汇报告对话框
│  ├─ paperhub_client.py           ← PaperHub AI 翻译核心
│  ├─ paperhub_confirm_dialog.py   ← AI 建议确认对话框
│  ├─ paperhub_settings.py         ← PaperHub + ASK模板 配置存取
│  ├─ paperhub_settings_dialog.py  ← PaperHub 设置对话框
│  ├─ parse_history_json.py        ← 翻译历史解析
│  ├─ parse_lexicon.py             ← JSON 词库解析
│  ├─ parse_mapping_csv.py         ← TTS 映射规则解析
│  ├─ parse_whitepaper.py          ← 白皮书 Markdown 解析
│  ├─ rule_translator.py           ← 规则翻译引擎
│  ├─ ssml_generator.py            ← SSML 语音标签生成
│  ├─ storage.py                   ← JSON 存储管理
│  ├─ ui_theme.py                  ← UI 主题 Token 系统
│  ├─ unmatched_words_dialog.py    ← 未匹配词汇处理对话框
│  └─ add_word_dialog.py           ← 旧版未匹配词添加（保留备用）
├─ assets/
│  ├─ app_icon.jpg                 ← 应用图标源文件（可替换 jpg/png/ico）
│  ├─ icons/
│  │  ├─ confirm.png               ← ✓ 确认图标
│  │  ├─ discard.png               ← ✗ 丢弃图标
│  │  ├─ copy.png                  ← ⎘ 复制图标（待补充）
│  │  └─ translate.png             ← ⟶ 翻译图标（待补充）
│  └─ lang_icons/                  ← 语言图标目录（用户放入 PNG/JPG 供选择）
│     ├─ 1F43E.png
│     └─ 1F47B.png
├─ data/
│  ├─ config.json                  ← 应用状态（语言列表含 id/name/folder/notes/icon）
│  ├─ <语言名>/                    ← 每语言独立子目录
│  │  ├─ whitepaper.md
│  │  ├─ Conlang_Master_Library.json
│  │  ├─ Mapping_Rules.csv
│  │  ├─ Translation_History.json
│  │  └─ derived/material_snapshot.json
│  └─ languages/                   ← 空目录（历史遗留，待清理）
├─ main.py                         ← 入口（4K DPI 适配 + 主题应用）
├─ app_config.json                 ← PaperHub + 字体 + ASK模板 配置（exe旁边）
├─ build.bat / build.spec          ← PyInstaller 构建
├─ 启动.bat                        ← 开发模式启动脚本
├─ requirements.txt
├─ DEVLOG.md                       ← 开发日志（完整待办清单）
├─ PROJECT_STATUS.md               ← 项目状态文档
├─ DATA_FORMAT_SPEC.md             ← 数据文件格式规范
└─ README.md
```

## 安装依赖

```bash
python -m venv venv
venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

## PaperHub AI 翻译配置

主窗口菜单 → 设置 → PaperHub 设置：
- API Key：从 [PaperHub 工作台](https://tc-paperhub.diezhi.net/dashboard) 获取
- 模型选择：qwen3-max / glm-5 / doubao-seed-2-0-pro / qwen3.5-plus 等
- 翻译策略：仅未匹配（推荐）/ 全部 AI / 候选确认
- Reasoning 模式开关 + Temperature / Max Tokens / Timeout / Stream

## 语言大师问答

- 快捷提问模板栏（默认预设 + 自定义管理）
- 多轮对话引擎（流式 chunk 接收 + Ctrl+Enter 发送）
- AI 回复自动解析【新词】格式 → 填入待审核表格
- Token 圆圈可视化（环形进度 + 用量/上限标签）
- 待审核机制：批量确认导入词库 / 批量丢弃 / 清空

## Excel 批量翻译

1. 导入 Excel 台本 → 预览 + 统计
2. 设置翻译模式（规则/混合/AI）+ 并发控制
3. 翻译完成 → 导出 Excel + 未匹配词汇报告 CSV + 新创词汇报告

## 主题与外观

- 菜单 → 设置 → 外观与主题：
  - 主题切换（马卡龙紫默认，后续可扩展深色主题）
  - 字体族选择（覆盖系统已安装字体）
  - 字号缩放（0.8× ~ 1.3×）
  - 偏好持久化到 `app_config.json`

## 语言图标

- 右键语言列表项 →「选择图标」
- 从 `assets/lang_icons/` 目录中选取 PNG/JPG 图片
- 图标路径保存到 `data/config.json` 的 `icon` 字段
- 清除图标可恢复默认状态

## 后续开发计划

详见 [DEVLOG.md](DEVLOG.md) 的完整待办清单，核心方向：
- 深色主题定版
- 翻译后 AI 朗读按钮
- SSML `<phoneme>` + `<break>` 增强
- ElevenLabs / Resemble AI 语音生成接入
- RVC 声音转换后处理
- 批量翻译续翻/缓存/限流优化
- 代码质量：LF行尾 / Translation_ID对齐 / 线程安全