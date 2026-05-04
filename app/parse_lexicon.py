from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

ZH_KEYS = frozenset(
    {
        "zh",
        "cn",
        "chinese",
        "中文",
        "source",
        "src",
        "han",
        "hanzi",
        "原文",
        "汉语",
    }
)
CON_KEYS = frozenset(
    {
        "conlang",
        "target",
        "tl",
        "translation",
        "译",
        "译本",
        "译词",
        "词",
        "词条",
        "自创语",
        "目标语",
    }
)

# 结构化词库元数据字段（值层 dict 中识别的字段名）
META_CONLANG_KEYS = ("conlang", "target", "tl", "自创语", "目标语")
META_POS_KEYS = ("pos", "词性", "part_of_speech")
META_STYLE_KEYS = ("style", "风格", "register", "tone")
META_SYNONYMS_KEYS = ("synonyms", "近义词", "syn")
META_FREQ_KEYS = ("freq", "frequency", "频率", "使用次数")
META_NOTES_KEYS = ("notes", "备注", "note", "说明")
META_CORE_KEYS = ("core", "is_core", "核心", "高频")


def _is_cjk_heavy(s: str) -> bool:
    return any("一" <= c <= "鿿" for c in s)


def _first_str(d: Dict[str, Any], keys) -> str:
    """从 dict 中按候选字段名顺序取第一个非空字符串值。"""
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _first_bool(d: Dict[str, Any], keys, default: bool = False) -> bool:
    for k in keys:
        if k in d:
            return bool(d[k])
    return default


def _first_int(d: Dict[str, Any], keys, default: int = 0) -> int:
    for k in keys:
        v = d.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            return int(v)
        if isinstance(v, str) and v.strip().lstrip("-").isdigit():
            return int(v.strip())
    return default


def _first_list(d: Dict[str, Any], keys) -> List[str]:
    for k in keys:
        v = d.get(k)
        if isinstance(v, list):
            out: List[str] = []
            for item in v:
                if isinstance(item, str) and item.strip():
                    out.append(item.strip())
            return out
    return []


def _is_meta_value_dict(d: Dict[str, Any]) -> bool:
    """判定一个 value dict 是否是「结构化条目」（而不是嵌套的子词库结构）。

    判据：含至少一个 conlang 字段。这避免把 {"entries": [...]} 误判为元数据。
    """
    if not isinstance(d, dict):
        return False
    return bool(_first_str(d, META_CONLANG_KEYS))


def _extract_meta(d: Dict[str, Any], conlang: str) -> Dict[str, Any]:
    """从结构化条目的 value dict 中提取元数据。"""
    return {
        "conlang": conlang,
        "pos": _first_str(d, META_POS_KEYS),
        "style": _first_str(d, META_STYLE_KEYS),
        "synonyms": _first_list(d, META_SYNONYMS_KEYS),
        "freq": _first_int(d, META_FREQ_KEYS, 0),
        "notes": _first_str(d, META_NOTES_KEYS),
        "core": _first_bool(d, META_CORE_KEYS, False),
    }


def _has_meaningful_meta(meta: Dict[str, Any]) -> bool:
    """元数据是否包含任何非默认字段（用于判断要不要存进 meta 索引）。"""
    return bool(
        meta.get("pos")
        or meta.get("style")
        or meta.get("synonyms")
        or meta.get("freq")
        or meta.get("notes")
        or meta.get("core")
    )


def _looks_like_outer_keyed_lexicon(data: Any) -> bool:
    """检测顶层是否为 {zh_key: str_or_meta_dict} 模式（新旧扁平词库）。"""
    if not isinstance(data, dict) or not data:
        return False
    cjk_outer = sum(1 for k in data if isinstance(k, str) and _is_cjk_heavy(k))
    if cjk_outer < max(1, len(data) // 4):
        return False
    # 每个 value 要么是非空 str 要么是含 conlang 字段的 dict
    for v in data.values():
        if isinstance(v, str):
            continue
        if isinstance(v, dict) and _is_meta_value_dict(v):
            continue
        return False
    return True


def _pick_zh_con_pair(obj: Dict[str, Any]) -> Tuple[str | None, str | None]:
    zh_val: str | None = None
    con_val: str | None = None
    lower_map = {str(k).lower(): (k, v) for k, v in obj.items() if isinstance(k, str)}
    for zk in ZH_KEYS:
        hit = lower_map.get(zk.lower())
        if hit and isinstance(hit[1], str) and hit[1].strip():
            zh_val = hit[1].strip()
            break
    for ck in CON_KEYS:
        hit = lower_map.get(ck.lower())
        if hit and isinstance(hit[1], str) and hit[1].strip():
            con_val = hit[1].strip()
            break
    if zh_val and con_val:
        return zh_val, con_val

    str_vals = [(str(k), str(v)) for k, v in obj.items() if isinstance(k, str) and isinstance(v, str)]
    cjk_keys = [(k, v) for k, v in str_vals if _is_cjk_heavy(k) and v.strip()]
    if len(cjk_keys) == 1:
        k, v = cjk_keys[0]
        return k.strip(), v.strip()

    return zh_val, con_val


def _walk_collect(obj: Any, acc: Dict[str, str]) -> None:
    if isinstance(obj, list):
        for item in obj:
            _walk_collect(item, acc)
        return
    if not isinstance(obj, dict):
        return

    zh, con = _pick_zh_con_pair(obj)
    if zh and con:
        acc.setdefault(zh, con)

    for v in obj.values():
        if isinstance(v, (dict, list)):
            _walk_collect(v, acc)

    for list_key in ("entries", "words", "items", "lexicon", "dictionary", "vocabulary"):
        child = obj.get(list_key)
        if isinstance(child, list):
            for item in child:
                _walk_collect(item, acc)


def _walk_collect_meta(obj: Any, flat: Dict[str, str], meta: Dict[str, Dict[str, Any]]) -> None:
    """递归收集模式下，同时尝试提取元数据（用于 entries-as-list 形式）。"""
    if isinstance(obj, list):
        for item in obj:
            _walk_collect_meta(item, flat, meta)
        return
    if not isinstance(obj, dict):
        return

    zh, con = _pick_zh_con_pair(obj)
    if zh and con:
        flat.setdefault(zh, con)
        # 同一 dict 内可能附带 pos/style 等元数据
        m = _extract_meta(obj, con)
        if _has_meaningful_meta(m) and zh not in meta:
            meta[zh] = m

    for v in obj.values():
        if isinstance(v, (dict, list)):
            _walk_collect_meta(v, flat, meta)

    for list_key in ("entries", "words", "items", "lexicon", "dictionary", "vocabulary"):
        child = obj.get(list_key)
        if isinstance(child, list):
            for item in child:
                _walk_collect_meta(item, flat, meta)


def build_lexicon_full(data: Any) -> Tuple[Dict[str, str], Dict[str, Dict[str, Any]]]:
    """同时构建扁平索引 + 结构化元数据索引。

    返回 (flat, meta)：
      - flat: {zh: conlang_str}，给翻译引擎用，行为与旧 build_lexicon_index 一致
      - meta: {zh: {conlang, pos, style, synonyms, freq, notes, core}}，仅含有非默认字段的条目

    支持三种文件形态：
      1) 新结构化：{"光": {"conlang": "lumi", "pos": "名词", ...}}
      2) 旧扁平：  {"光": "lumi"}
      3) 嵌套列表：{"entries": [{"zh": "光", "conlang": "lumi", "pos": "名词"}, ...]}
    """
    flat: Dict[str, str] = {}
    meta: Dict[str, Dict[str, Any]] = {}

    # 模式 A：外键即中文（新结构化 + 旧扁平 + 混合）
    if isinstance(data, dict) and _looks_like_outer_keyed_lexicon(data):
        for zh, v in data.items():
            zh_key = str(zh).strip()
            if not zh_key:
                continue
            if isinstance(v, str):
                if v.strip():
                    flat[zh_key] = v.strip()
            elif isinstance(v, dict):
                conlang = _first_str(v, META_CONLANG_KEYS)
                if not conlang:
                    continue
                flat[zh_key] = conlang
                m = _extract_meta(v, conlang)
                if _has_meaningful_meta(m):
                    meta[zh_key] = m
        if flat:
            return flat, meta

    # 模式 B：递归收集（兼容旧 entries-as-list 等嵌套形态）
    _walk_collect_meta(data, flat, meta)
    return flat, meta


def build_lexicon_index(data: Any) -> Dict[str, str]:
    """向后兼容接口：仅返回扁平索引。"""
    flat, _meta = build_lexicon_full(data)
    return flat


def load_master_library(path: Path) -> Tuple[Dict[str, str], int, Any]:
    """向后兼容接口：返回 (flat, count, raw)。"""
    raw_text = path.read_text(encoding="utf-8-sig")
    data = json.loads(raw_text)
    index = build_lexicon_index(data)
    return index, len(index), data


def load_master_library_full(
    path: Path,
) -> Tuple[Dict[str, str], Dict[str, Dict[str, Any]], int, Any]:
    """新接口：返回 (flat, meta, count, raw)。"""
    raw_text = path.read_text(encoding="utf-8-sig")
    data = json.loads(raw_text)
    flat, meta = build_lexicon_full(data)
    return flat, meta, len(flat), data


def serialize_lexicon_entry(
    conlang: str,
    meta: Dict[str, Any] | None = None,
) -> Any:
    """规范化序列化单条词库条目，供写盘代码使用以保证前向兼容。

    若 meta 为空或所有字段都是默认值，返回 conlang 字符串（扁平）；
    否则返回结构化 dict。这样旧版本客户端仍能读取无元数据的条目。
    """
    conlang = str(conlang or "").strip()
    if not conlang:
        return ""
    if not meta:
        return conlang
    norm = {
        "conlang": conlang,
        "pos": str(meta.get("pos") or "").strip(),
        "style": str(meta.get("style") or "").strip(),
        "core": bool(meta.get("core", False)),
        "synonyms": [str(s).strip() for s in (meta.get("synonyms") or []) if str(s).strip()],
        "freq": int(meta.get("freq") or 0) if not isinstance(meta.get("freq"), bool) else 0,
        "notes": str(meta.get("notes") or "").strip(),
    }
    if not _has_meaningful_meta(norm):
        return conlang
    # 仅写出非空字段，让文件保持精简
    out: Dict[str, Any] = {"conlang": conlang}
    for k in ("pos", "style", "notes"):
        if norm[k]:
            out[k] = norm[k]
    if norm["core"]:
        out["core"] = True
    if norm["synonyms"]:
        out["synonyms"] = norm["synonyms"]
    if norm["freq"]:
        out["freq"] = norm["freq"]
    return out

