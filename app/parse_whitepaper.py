from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _iter_sections(text: str) -> List[Tuple[str, str]]:
    """按 Markdown 风格标题切分为 (标题, 正文)。"""
    lines = text.splitlines()
    title = "序言"
    buf: List[str] = []
    sections: List[Tuple[str, str]] = []

    def flush() -> None:
        nonlocal buf
        if buf or title:
            sections.append((title, "\n".join(buf).strip()))
        buf = []

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            flush()
            title = m.group(2).strip()
            buf = []
        else:
            buf.append(line)
    flush()
    return sections


def _parse_md_table_rows(block_lines: List[str]) -> List[List[str]]:
    rows: List[List[str]] = []
    for raw in block_lines:
        line = raw.strip()
        if not line.startswith("|"):
            continue
        if re.match(r"^\|[\s\-:|]+\|$", line):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 2 and parts[0] == "" and parts[-1] == "":
            parts = parts[1:-1]
        if parts:
            rows.append(parts)
    return rows


def _extract_tables(body: str) -> List[List[List[str]]]:
    tables: List[List[List[str]]] = []
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            block: List[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            if len(block) >= 2:
                rows = _parse_md_table_rows(block)
                if rows:
                    tables.append(rows)
            continue
        i += 1
    return tables


def _row_mentions_phoneme_header(row: List[str]) -> bool:
    joined = " ".join(row)
    return "IPA" in joined or "音位" in joined


def _extract_phoneme_tables(body: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for table in _extract_tables(body):
        if not table:
            continue
        header = table[0]
        if _row_mentions_phoneme_header(header) or any(_row_mentions_phoneme_header(r) for r in table[:3]):
            data_rows = table[1:] if _row_mentions_phoneme_header(header) else table
            phonemes: List[Dict[str, str]] = []
            headers = header if _row_mentions_phoneme_header(header) else [f"col_{idx}" for idx in range(len(table[0]))]
            for r in data_rows:
                if not any(cell.strip() for cell in r):
                    continue
                row_obj: Dict[str, str] = {}
                for idx, cell in enumerate(r):
                    if idx < len(headers):
                        key = headers[idx].strip() or f"col_{idx}"
                    else:
                        key = f"col_{idx}"
                    row_obj[key] = cell.strip()
                phonemes.append(row_obj)
            out.append({"header": header, "rows": phonemes})
    return out


def _is_candidate_rule_line(line: str) -> bool:
    t = line.strip()
    if not t or t.startswith("#"):
        return False
    if re.match(r"^[-*•·]\s+", t):
        return True
    if re.match(r"^\d+[\.\)、]\s+", t):
        return True
    if re.match(r"^[（(]\d+[）)]\s*", t):
        return True
    return False


def _extract_grammar_rules(body: str) -> List[str]:
    rules: List[str] = []
    for line in body.splitlines():
        if _is_candidate_rule_line(line):
            rules.append(line.strip())
    if rules:
        return rules
    # 无列表样式时退化为非空行（截断避免把散文整段当规则）
    fallback: List[str] = []
    for line in body.splitlines():
        t = line.strip()
        if t and not t.startswith("#") and len(t) < 400:
            fallback.append(t)
        if len(fallback) >= 80:
            break
    return fallback


def parse_whitepaper(text: str) -> Dict[str, Any]:
    """解析白皮书为结构化字典（启发式，适配常见 Markdown 标题与表格）。"""
    sections = _iter_sections(text)
    grammar_chunks: List[str] = []
    morphology_chunks: List[str] = []
    syntax_chunks: List[str] = []

    raw_sections: Dict[str, str] = {}

    for sec_title, body in sections:
        raw_sections[sec_title] = body
        if "语法" in sec_title:
            grammar_chunks.append(body)
        if "句法" in sec_title:
            syntax_chunks.append(body)
        if "构词" in sec_title:
            morphology_chunks.append(body)

    full_text = text
    phoneme_tables = _extract_phoneme_tables(full_text)

    grammar_rules: List[str] = []
    for chunk in grammar_chunks + syntax_chunks:
        grammar_rules.extend(_extract_grammar_rules(chunk))

    morphology_rules: List[str] = []
    for chunk in morphology_chunks:
        morphology_rules.extend(_extract_grammar_rules(chunk))

    phoneme_rows = sum(len(t["rows"]) for t in phoneme_tables)

    return {
        "version": 1,
        "phoneme_tables": phoneme_tables,
        "phoneme_row_count": phoneme_rows,
        "grammar_rules": grammar_rules,
        "grammar_rule_count": len(grammar_rules),
        "morphology_rules": morphology_rules,
        "morphology_rule_count": len(morphology_rules),
        "sections": raw_sections,
    }
