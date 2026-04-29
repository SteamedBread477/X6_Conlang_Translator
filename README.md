# Nikki Conlang Forge

`Nikki Conlang Forge`（无限暖暖自创语翻译器）是一个使用 Python + PyQt5 构建的桌面自创语翻译器，支持规则翻译与 PaperHub AI 辅助翻译。

## 功能概览

- 多语言页签管理（添加、重命名、删除、备注）
- 四种语言资料文件导入（白皮书 / 词库 / 映射规则 / 翻译历史）
- 规则翻译引擎（词库最长匹配 → TTS 音译 → 翻译历史记录）
- PaperHub AI 辅助翻译（三种策略：仅未匹配 / 全部 / 候选确认）
- AI 新词建议与词库入库
- 语言包 ZIP 导出/导入
- 未匹配词添加对话框

## 项目结构

```text
X6_Conlang_Translator/
├─ app/
│  ├─ __init__.py
│  ├─ add_word_dialog.py           ← 未匹配词添加对话框
│  ├─ asset_validation.py          ← 资料文件校验
│  ├─ history_writer.py            ← 翻译历史写入
│  ├─ import_classify.py           ← 文件类型自动识别
│  ├─ lexicon_segment.py           ← 词库最长匹配分词
│  ├─ main_window.py               ← 主窗口（异步翻译线程+confirm对话框）
│  ├─ material_service.py          ← 资料导入/解析流水线
│  ├─ paperhub_client.py           ← PaperHub AI 翻译核心
│  ├─ paperhub_confirm_dialog.py   ← AI 建议确认对话框
│  ├─ paperhub_settings.py         ← PaperHub 配置存取
│  ├─ paperhub_settings_dialog.py  ← PaperHub 设置对话框
│  ├─ parse_history_json.py        ← 翻译历史解析
│  ├─ parse_lexicon.py             ← JSON 词库解析
│  ├─ parse_mapping_csv.py         ← TTS 映射规则解析
│  ├─ parse_whitepaper.py          ← 白皮书 Markdown 解析
│  ├─ rule_translator.py           ← 规则翻译引擎
│  ├─ storage.py                   ← JSON 存储管理
│  └─ ui_theme.py                  ← UI 主题/颜色常量
├─ data/
│  ├─ app_config.json              ← PaperHub AI 配置
│  ├─ config.json                  ← 应用状态
│  └─ <语言资料夹>/ ...
├─ main.py                         ← 入口
├─ PROJECT_STATUS.md               ← 项目状态文档
├─ README.md
├─ requirements.txt
└─ X6_Conlang_Translator_PROJECT_STATUS.md ← 续聊入口文档
```

## 安装依赖

```bash
# 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate    # Windows
# source venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

## PaperHub AI 翻译配置

在主窗口菜单 → 设置 → PaperHub 设置 中配置：
- API Key：从 [PaperHub 工作台](https://tc-paperhub.diezhi.net/dashboard) 获取
- 模型选择：qwen3-max / glm-5 / doubao-seed-2-0-pro / qwen3.5-plus 等
- 翻译策略：
  - **仅未匹配**：先规则翻译，词库外片段由 AI 补全（推荐）
  - **全部 AI**：整句由 AI 翻译，参考词库保持一致性
  - **候选确认**：AI 生成候选翻译，弹出对话框让用户确认或修改

## 后续开发计划

- 阶段七：Excel 批量翻译（openpyxl 读取/写入，进度条，中断续翻）