"""主词库 JSON 写盘的唯一入口。

设计目的：
  之前三处独立的写盘逻辑（add_word_dialog / main_window 新词入库 /
  batch_translator 自动入库）各自重复实现"读旧文件 → 合并新条目 → 写回"。
  任何字段升级（如 TC-300 引入的元数据 pos/style/core）都要改 N 处，
  并且每处都裸写 dict 容易漏掉前向兼容、atomic write 等细节。

  本模块把这层粘合逻辑抽出，提供：
    - LexiconEntry：AI prompt 可见的元数据（pos/style/core/synonyms/freq/notes）
    - AuditRecord：供溯源 sidecar 写到 master_data["vocabulary"][zh] 的字段
                    （ipa/tts/logic/created_by/created_time/model/source）
                    这些字段不参与 AI prompt，仅做记录
    - upsert_entries：原子合并写入

兼容性：
  - 顶层条目：元数据全为默认值时写扁平 str；任一字段非空时写结构化 dict
    （TC-300 兼容矩阵：旧客户端可读扁平条目，跳过 dict 条目）
  - 文件已是 list 形态（旧 entries-as-list 风格）时保留 list 形态
  - 任何无法解析的字段（如未知 root key）原样保留，不丢失
  - 写入采用 .tmp 文件 + os.replace，写中途断电/崩溃不破坏老文件
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.parse_lexicon import serialize_lexicon_entry


@dataclass
class LexiconEntry:
    """词库条目。zh + conlang 必填；其余字段非空时进 prompt-side 元数据。"""
    zh: str
    conlang: str
    pos: str = ""
    style: str = ""
    core: bool = False
    synonyms: List[str] = field(default_factory=list)
    freq: int = 0
    notes: str = ""


@dataclass
class AuditRecord:
    """审计/溯源 sidecar 记录。写入 master_data['vocabulary'][zh]，不参与 AI prompt。

    用途：batch_translator 与 unmatched_words 把 AI 创造词的 IPA/TTS/构词逻辑/
    创建者/模型/时间戳记到 sidecar，方便用户事后审查"这个词从哪来"。
    """
    ipa: str = ""
    tts: str = ""
    logic: str = ""
    created_by: str = ""
    created_time: str = ""
    model: str = ""
    source: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k in ("ipa", "tts", "logic", "created_by", "created_time", "model", "source"):
            v = getattr(self, k)
            if v:
                out[k] = v
        if self.extra:
            for k, v in self.extra.items():
                if k not in out:
                    out[k] = v
        return out


@dataclass
class WriteReport:
    """upsert_entries 的返回值。"""
    written_count: int = 0
    new_count: int = 0
    updated_count: int = 0
    target_path: str = ""
    file_format: str = "dict"  # "dict" / "list"


def _read_existing(master_path: Path) -> Any:
    """读取已有词库文件；不存在 / 空 / 损坏时返回 {}。"""
    if not master_path.is_file():
        return {}
    raw = master_path.read_text(encoding="utf-8-sig").strip()
    if not raw or raw == "{}":
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 保守处理：损坏文件不要静默覆盖，让调用方决定（这里返回 {} 等价于
        # "把它当空"——和现有三处实现的行为一致）
        return {}


def _atomic_write_json(target: Path, data: Any) -> None:
    """原子写入：写到同目录 .tmp 文件，flush+fsync 后 os.replace 覆盖目标。

    Windows 上 os.replace 是原子的；Unix 上同 fs 的 rename 也原子。
    写到同目录是必要的——跨 fs 的 rename 不原子。
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)

    fd, tmp_name = tempfile.mkstemp(
        prefix=target.name + ".",
        suffix=".tmp",
        dir=str(target.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                # Windows / 某些 fs 上 fsync 失败可忽略，原子性由 replace 保证
                pass
        os.replace(tmp_path, target)
    except Exception:
        # 写失败时尽力清理 .tmp
        try:
            if tmp_path.is_file():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def _entry_to_serialized(entry: LexiconEntry) -> Any:
    """把 LexiconEntry 转成将要写入文件的值（str 或 dict，按元数据是否非空）。"""
    meta = {
        "pos": entry.pos,
        "style": entry.style,
        "core": entry.core,
        "synonyms": entry.synonyms,
        "freq": entry.freq,
        "notes": entry.notes,
    }
    return serialize_lexicon_entry(entry.conlang, meta)


def upsert_entries(
    master_path: Path,
    entries: List[LexiconEntry],
    *,
    audit_records: Optional[Dict[str, AuditRecord]] = None,
) -> WriteReport:
    """将词条 upsert 到主词库 JSON。

    参数：
      master_path：目标 Conlang_Master_Library.json 路径
      entries：要写入的词条列表（zh 重复时后者覆盖前者）
      audit_records：可选；{zh: AuditRecord} 写入 master_data['vocabulary'][zh]
                     供未来溯源界面读取，不影响翻译路径

    行为：
      - 已有文件是 dict（包含扁平 / 结构化 / 混合）：merge 到顶层
      - 已有文件是 list：append 到 list 末尾，避免破坏既有形态
      - 已有文件不存在 / 空 / 损坏：新建 dict
      - 顶层条目按元数据是否非空决定 str / dict（前向兼容）
      - 写入原子：.tmp + os.replace
    """
    if not entries:
        return WriteReport(target_path=str(master_path))

    data = _read_existing(master_path)
    new_count = 0
    updated_count = 0
    file_format = "dict"

    if isinstance(data, list):
        file_format = "list"
        existing_zh = {
            (item.get("zh") or item.get("中文") or item.get("source"))
            for item in data
            if isinstance(item, dict)
        }
        for entry in entries:
            zh = entry.zh.strip()
            if not zh or not entry.conlang.strip():
                continue
            if zh in existing_zh:
                # list 形态下 upsert 语义为追加（与既有实现一致），重复 zh 跳过
                continue
            item: Dict[str, Any] = {"zh": zh, "conlang": entry.conlang}
            if entry.pos:
                item["pos"] = entry.pos
            if entry.style:
                item["style"] = entry.style
            if entry.core:
                item["core"] = True
            if entry.synonyms:
                item["synonyms"] = entry.synonyms
            if entry.freq:
                item["freq"] = entry.freq
            if entry.notes:
                item["notes"] = entry.notes
            data.append(item)
            existing_zh.add(zh)
            new_count += 1
    else:
        if not isinstance(data, dict):
            data = {}
        for entry in entries:
            zh = entry.zh.strip()
            if not zh or not entry.conlang.strip():
                continue
            already = zh in data
            data[zh] = _entry_to_serialized(entry)
            if already:
                updated_count += 1
            else:
                new_count += 1

        # 审计 sidecar：写入 master_data['vocabulary'][zh]
        if audit_records:
            vocab = data.get("vocabulary")
            if not isinstance(vocab, dict):
                vocab = {}
            for entry in entries:
                rec = audit_records.get(entry.zh.strip())
                if rec is None:
                    continue
                rec_dict = rec.to_dict()
                if not rec_dict:
                    continue
                # sidecar 中也带上 conlang，便于审计界面单独显示
                rec_dict.setdefault("conlang", entry.conlang)
                vocab[entry.zh.strip()] = rec_dict
            if vocab:
                data["vocabulary"] = vocab

    _atomic_write_json(master_path, data)

    return WriteReport(
        written_count=new_count + updated_count,
        new_count=new_count,
        updated_count=updated_count,
        target_path=str(master_path),
        file_format=file_format,
    )
