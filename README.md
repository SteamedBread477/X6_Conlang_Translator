# Nikki Conlang Forge

`Nikki Conlang Forge` 是一个使用 Python + PyQt5 构建的桌面自创语翻译器。

当前阶段（阶段零）已完成：

- 项目基础目录结构
- 可运行的 PyQt5 主窗口
- 多语言页签的添加与重命名
- 基于 JSON 的应用状态存储
- 单句翻译区与批量翻译区的界面预留
- 四种语言资料文件的导入入口

## 项目结构

```text
X6_Conlang_Translator/
├─ app/
│  ├─ __init__.py
│  ├─ asset_validation.py
│  ├─ import_classify.py
│  ├─ material_service.py
│  ├─ parse_history_json.py
│  ├─ parse_lexicon.py
│  ├─ parse_mapping_csv.py
│  ├─ parse_whitepaper.py
│  ├─ main_window.py
│  ├─ storage.py
│  └─ ui_theme.py
├─ data/
│  ├─ config.json
│  └─ <语言资料夹>/
│     ├─ derived/material_snapshot.json
│     └─ …标准资料文件…
├─ main.py
├─ README.md
└─ requirements.txt
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

## 后续建议

下一阶段建议优先做下面三件事：

1. 定义四种资料文件的严格数据校验规则
2. 先实现“导入资料并保存到语言页签”
3. 再实现“中文 -> 自创语”的可替换翻译流水线

这样后面做批量 Excel 翻译时，结构会更稳，不容易推倒重来。
