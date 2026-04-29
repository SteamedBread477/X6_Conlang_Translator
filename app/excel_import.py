"""
Excel 台本导入模块（阶段八）。

读取 .xlsx 文件，验证必需列，提供预览与统计信息。

必需列（首行为表头）：
  台本ID, Character, Age, Gender, Body_Type, Emotion, Scene_Context, Text

后续列可能更新，因此不写死列顺序——只验证必需列是否存在，
其余列原样保留供后续使用。

公开接口：
  ExcelImportResult — 导入结果数据结构
  read_excel(path) -> ExcelImportResult
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# 必需列名（不写死顺序，只检查是否存在）
REQUIRED_COLUMNS: List[str] = [
    "台本ID",
    "Character",
    "Age",
    "Gender",
    "Body_Type",
    "Emotion",
    "Scene_Context",
    "Text",
]


@dataclass
class ExcelRow:
    """Excel 中的一行数据。"""
    data: Dict[str, Any]  # 列名 → 值（包含必需列和额外列）


@dataclass
class ExcelStatistics:
    """Excel 台本统计信息。"""
    total_rows: int = 0
    character_count: int = 0
    characters: List[str] = field(default_factory=list)
    emotion_types: List[str] = field(default_factory=list)
    emotion_count: int = 0


@dataclass
class ExcelImportResult:
    """Excel 导入结果。"""
    ok: bool = False
    path: str = ""
    rows: List[ExcelRow] = field(default_factory=list)
    columns: List[str] = field(default_factory=list)
    missing_columns: List[str] = field(default_factory=list)
    statistics: ExcelStatistics = field(default_factory=ExcelStatistics)
    preview_rows: List[ExcelRow] = field(default_factory=list)
    error: str = ""


def read_excel(path: str) -> ExcelImportResult:
    """
    读取 Excel 台本文件，验证必需列，计算统计信息。

    返回 ExcelImportResult：
      - ok=True 时 rows / statistics / preview_rows 均可用
      - ok=False 时 error 字段包含错误描述
      - missing_columns 列出缺失的必需列
    """
    if not path:
        return ExcelImportResult(error="未选择文件。")

    p = Path(path)
    if not p.is_file():
        return ExcelImportResult(error=f"文件不存在：{path}")

    if p.suffix.lower() not in (".xlsx", ".xls"):
        return ExcelImportResult(error="仅支持 .xlsx / .xls 格式的 Excel 文件。")

    try:
        import pandas as pd
    except ImportError:
        return ExcelImportResult(
            error="缺少 pandas / openpyxl 包，请执行：pip install pandas openpyxl"
        )

    try:
        df = pd.read_excel(p, engine="openpyxl")
    except Exception as exc:
        return ExcelImportResult(error=f"读取 Excel 失败：{exc}")

    if df.empty:
        return ExcelImportResult(
            ok=True,
            path=path,
            rows=[],
            columns=list(df.columns),
            statistics=ExcelStatistics(total_rows=0),
            preview_rows=[],
        )

    # 获取所有列名
    all_columns: List[str] = [str(c) for c in df.columns]

    # 验证必需列
    missing: List[str] = [c for c in REQUIRED_COLUMNS if c not in all_columns]

    # 将 DataFrame 转为 ExcelRow 列表
    rows: List[ExcelRow] = []
    for _, row_data in df.iterrows():
        row_dict: Dict[str, Any] = {}
        for col in all_columns:
            val = row_data.get(col)
            # 处理 NaN
            if val is not None and not (isinstance(val, float) and str(val) == "nan"):
                row_dict[col] = str(val).strip()
            else:
                row_dict[col] = ""
        rows.append(ExcelRow(data=row_dict))

    # 统计信息
    characters: Set[str] = set()
    emotions: Set[str] = set()
    for row in rows:
        ch = row.data.get("Character", "")
        if ch:
            characters.add(ch)
        em = row.data.get("Emotion", "")
        if em:
            emotions.add(em)

    stats = ExcelStatistics(
        total_rows=len(rows),
        character_count=len(characters),
        characters=sorted(characters),
        emotion_types=sorted(emotions),
        emotion_count=len(emotions),
    )

    # 预览：前5行
    preview = rows[:5]

    return ExcelImportResult(
        ok=True,
        path=path,
        rows=rows,
        columns=all_columns,
        missing_columns=missing,
        statistics=stats,
        preview_rows=preview,
    )


def get_texts_from_rows(rows: List[ExcelRow]) -> List[str]:
    """提取所有行的 Text 列内容（非空行）。"""
    result: List[str] = []
    for row in rows:
        text = row.data.get("Text", "")
        if text.strip():
            result.append(text.strip())
    return result