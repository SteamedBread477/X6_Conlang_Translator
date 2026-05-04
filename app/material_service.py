from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

import json
import shutil

from app.import_classify import (
    FILE_KEY_HISTORY,
    FILE_KEY_MAPPING,
    FILE_KEY_MASTER,
    FILE_KEY_WHITE,
    classify_import_path,
)
from app.parse_history_json import load_translation_anchors
from app.parse_lexicon import load_master_library_full
from app.parse_mapping_csv import load_ipa_mapping, load_tts_mapping
from app.parse_whitepaper import parse_whitepaper

SNAPSHOT_VERSION = 1
SNAPSHOT_FILENAME = "material_snapshot.json"


@dataclass
class MaterialImportReport:
    lines: List[str] = field(default_factory=list)
    bundle: Dict[str, Any] = field(default_factory=dict)
    copy_warnings: List[str] = field(default_factory=list)


def _snapshot_path(storage: Any, language: Dict[str, Any]) -> Path:
    return storage.language_dir(language) / "derived" / SNAPSHOT_FILENAME


def load_snapshot_if_any(storage: Any, language: Dict[str, Any]) -> Dict[str, Any]:
    p = _snapshot_path(storage, language)
    if not p.is_file():
        return {}
    with p.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def save_snapshot(storage: Any, language: Dict[str, Any], bundle: Dict[str, Any]) -> None:
    dest = _snapshot_path(storage, language)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as handle:
        json.dump(bundle, handle, ensure_ascii=False, indent=2)


def rebuild_bundle_from_disk(storage: Any, language: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    parse_notes: List[str] = []
    bundle: Dict[str, Any] = {
        "version": SNAPSHOT_VERSION,
        "language_id": language.get("id"),
        "whitepaper": {},
        "lexicon": {},
        "lexicon_meta": {},
        "tts_map": {},
        "ipa_map": {},
        "anchors": {},
        "summary": {},
    }

    wp = storage.asset_path(language, "whitepaper")
    if wp.is_file():
        try:
            text = wp.read_text(encoding="utf-8-sig")
            parsed = parse_whitepaper(text)
            bundle["whitepaper"] = parsed
            bundle["summary"]["phoneme_row_count"] = parsed.get("phoneme_row_count", 0)
            bundle["summary"]["grammar_rule_count"] = parsed.get("grammar_rule_count", 0)
        except OSError as exc:
            parse_notes.append(f"白皮书读取失败：{exc}")
        except Exception as exc:
            parse_notes.append(f"白皮书解析失败：{exc}")

    master = storage.asset_path(language, "master_library")
    if master.is_file():
        try:
            flat, meta_idx, n, _raw = load_master_library_full(master)
            bundle["lexicon"] = flat
            bundle["lexicon_meta"] = meta_idx
            bundle["summary"]["lexicon_count"] = n
        except Exception as exc:
            parse_notes.append(f"主词库 JSON 无效或无法索引：{exc}")

    mapping = storage.asset_path(language, "mapping_rules")
    if mapping.is_file():
        try:
            tts, n = load_tts_mapping(mapping)
            bundle["tts_map"] = tts
            bundle["summary"]["mapping_count"] = n
            ipa, ni = load_ipa_mapping(mapping)
            bundle["ipa_map"] = ipa
            bundle["summary"]["ipa_count"] = ni
        except Exception as exc:
            parse_notes.append(f"映射表解析失败：{exc}")

    history = storage.asset_path(language, "translation_history")
    if history.is_file():
        try:
            anchors, n = load_translation_anchors(history)
            bundle["anchors"] = anchors
            bundle["summary"]["anchor_count"] = n
        except Exception as exc:
            parse_notes.append(f"翻译历史解析失败：{exc}")

    return bundle, parse_notes


def _match_parse_note(parse_notes: List[str], keyword: str) -> str | None:
    for note in parse_notes:
        if keyword in note:
            return note
    return None


def _format_user_lines(
    bundle: Dict[str, Any],
    parse_notes: List[str],
    *,
    expected_keys: set[str] | None = None,
) -> List[str]:
    """按需求输出 ✓/✗ 行；expected_keys 仅用在「刚导入」场景，避免对未触碰类型误报。"""
    lines: List[str] = []
    summary = bundle.get("summary") or {}
    if expected_keys is None:
        expected_keys = {FILE_KEY_MASTER, FILE_KEY_MAPPING, FILE_KEY_HISTORY, FILE_KEY_WHITE}

    if FILE_KEY_MASTER in expected_keys:
        err = _match_parse_note(parse_notes, "主词库")
        if err:
            lines.append(f"✗ 词库加载失败 - {err}")
        elif "lexicon_count" in summary:
            lines.append(f"✓ 词库已加载 - {int(summary['lexicon_count'])} 个词汇")

    if FILE_KEY_MAPPING in expected_keys:
        err = _match_parse_note(parse_notes, "映射表")
        if err:
            lines.append(f"✗ 映射规则加载失败 - {err}")
        elif "mapping_count" in summary:
            lines.append(f"✓ 映射规则已加载 - {int(summary.get('mapping_count') or 0)} 条规则")

    if FILE_KEY_HISTORY in expected_keys:
        err = _match_parse_note(parse_notes, "翻译历史")
        if err:
            lines.append(f"✗ 翻译历史加载失败 - {err}")
        elif "anchor_count" in summary:
            lines.append(f"✓ 翻译历史已加载 - {int(summary.get('anchor_count') or 0)} 条记录")

    if FILE_KEY_WHITE in expected_keys:
        err = _match_parse_note(parse_notes, "白皮书")
        if err:
            lines.append(f"✗ 白皮书解析失败 - {err}")
        elif bundle.get("whitepaper"):
            ph = int((bundle["whitepaper"] or {}).get("phoneme_row_count") or 0)
            gr = int((bundle["whitepaper"] or {}).get("grammar_rule_count") or 0)
            lines.append(f"✓ 白皮书已加载 - 含 {ph} 个音位、{gr} 条语法规则")

    return lines


def import_material_files(
    storage: Any,
    language: Dict[str, Any],
    source_paths: List[str],
) -> MaterialImportReport:
    """多选导入：按文件名识别类型，复制到标准名，解析并写入 derived/material_snapshot.json。"""
    grouped: Dict[str, List[Path]] = defaultdict(list)
    unknown: List[str] = []

    for raw in source_paths:
        p = Path(raw)
        if not p.is_file():
            unknown.append(raw)
            continue
        key = classify_import_path(p)
        if key:
            grouped[key].append(p)
        else:
            unknown.append(str(p))

    copy_warnings: List[str] = []
    touched: set[str] = set()
    for key, plist in grouped.items():
        touched.add(key)
        if len(plist) > 1:
            copy_warnings.append(f"类型「{key}」收到 {len(plist)} 个文件，已采用：{plist[-1].name}")
        src = plist[-1]
        dest = storage.asset_path(language, key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    bundle, parse_notes = rebuild_bundle_from_disk(storage, language)
    save_snapshot(storage, language, bundle)

    report_lines: List[str] = []
    for w in copy_warnings:
        report_lines.append(f"※ {w}")
    for u in unknown:
        report_lines.append(f"○ 已跳过（无法识别）：{Path(u).name}")

    if touched:
        report_lines.extend(_format_user_lines(bundle, parse_notes, expected_keys=touched))
    else:
        report_lines.extend(
            _format_user_lines(
                bundle,
                parse_notes,
                expected_keys=set(),
            )
        )

    return MaterialImportReport(lines=report_lines, bundle=bundle, copy_warnings=copy_warnings)


def refresh_materials_from_disk(storage: Any, language: Dict[str, Any]) -> MaterialImportReport:
    """语言包已更新磁盘（如 zip 解压）后调用：重新解析并保存快照。"""
    bundle, parse_notes = rebuild_bundle_from_disk(storage, language)
    save_snapshot(storage, language, bundle)
    lines = _format_user_lines(
        bundle,
        parse_notes,
        expected_keys={FILE_KEY_MASTER, FILE_KEY_MAPPING, FILE_KEY_HISTORY, FILE_KEY_WHITE},
    )
    return MaterialImportReport(lines=lines, bundle=bundle, copy_warnings=[])
