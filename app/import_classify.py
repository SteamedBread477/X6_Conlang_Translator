from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

# 与 storage.FILENAME_BY_KEY 逻辑键一致
FILE_KEY_WHITE = "whitepaper"
FILE_KEY_MASTER = "master_library"
FILE_KEY_MAPPING = "mapping_rules"
FILE_KEY_HISTORY = "translation_history"


def classify_import_path(path: Path) -> Optional[str]:
    """根据文件名识别资料类型；无法识别则返回 None。"""
    name = path.name
    lower = name.lower()

    if re.search(r"_Conlang_Master_Library\.json$", name, flags=re.IGNORECASE):
        return FILE_KEY_MASTER
    if re.search(r"_Mapping_Rules\.csv$", name, flags=re.IGNORECASE):
        return FILE_KEY_MAPPING
    if re.search(r"_Translation_History\.json$", name, flags=re.IGNORECASE):
        return FILE_KEY_HISTORY
    if "白皮书" in name or "whitepaper" in lower:
        return FILE_KEY_WHITE

    return None
