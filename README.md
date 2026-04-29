# Nikki Conlang Forge

`Nikki Conlang Forge`（无限暖暖自创语翻译器）是一个使用 Python + PyQt5 构建的桌面自创语翻译器，支持规则翻译、PaperHub AI 辅助翻译、未匹配词汇 AI 处理、Excel 台本批量翻译。

## 功能概览

- 多语言页签管理（添加、重命名、删除、备注）
- 四种语言资料文件导入（白皮书 / 词库 / 映射规则 / 翻译历史）
- 规则翻译引擎（词库最长匹配 → TTS 音译 → 翻译历史记录）
- PaperHub AI 辅助翻译（三种策略：仅未匹配 / 全部 / 候选确认）
- AI 新词建议与词库入库
- 未匹配词汇 AI 处理对话框（手动填写 / 单词AI / 批量AI / 保存到词库）
- Excel 台本批量翻译（导入→预览→统计→设置→翻译→导出）
- 批量翻译设置（规则/混合/AI模式、模型选择、并发控制、自动添加新词）
- 翻译结果导出为 Excel + 未匹配词汇报告 CSV
- 语言包 ZIP 导出/导入

## 项目结构

```text
X6_Conlang_Translator/
├─ app/
│  ├─ __init__.py
│  ├─ add_word_dialog.py           ← 未匹配词添加对话框（旧版，保留）
│  ├─ asset_validation.py          ← 资料文件校验
│  ├─ batch_translate_dialog.py    ← 批量翻译设置对话框
│  ├─ batch_translator.py          ← 批量翻译引擎+导出
│  ├─ excel_import.py              ← Excel台本导入+验证+统计+预览
│  ├─ history_writer.py            ← 翻译历史写入
│  ├─ import_classify.py           ← 文件类型自动识别
│  ├─ lexicon_segment.py           ← 词库最长匹配分词
│  ├─ main_window.py               ← 主窗口（翻译+批量+AI+未匹配词）
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
│  ├─ unmatched_words_dialog.py    ← 未匹配词汇处理对话框
│  └─ ui_theme.py                  ← UI 主题/颜色常量
├─ data/
│  ├─ app_config.json              ← PaperHub AI 配置
│  ├─ config.json                  ← 应用状态
│  └─ languages/
│     └─ <语言资料夹>/ ...
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

## Excel 批量翻译

1. 点击「选择 Excel」导入台本文件（.xlsx）
2. 预览对话框显示前5行数据 + 统计信息（总行数/角色数量/情绪类型）
3. 点击「开始翻译」弹出设置对话框：
   - 翻译模式：规则翻译 / 混合翻译 / AI翻译
   - 并发控制：请求数（1-5）+ 间隔时间（0-10秒）
4. 翻译完成后点击「导出文件」保存翻译结果 Excel
5. 未匹配词汇自动弹出处理对话框或导出为 CSV 报告

## 后续开发计划

- 阶段九：TTS 批量生成 / 批量翻译增强 / UI 美化 / 代码清理