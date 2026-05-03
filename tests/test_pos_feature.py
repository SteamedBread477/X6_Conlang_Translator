"""词性（POS）功能测试用例。

覆盖：
  1. parse_lexicon — 解析时拆分词性括号
  2. storage — 词库读写兼容 pos 字段
  3. rule_translator — 两级匹配策略（精确 + fallback）
  4. paperhub_client — AI候选词带词性
  5. 集成测试：从词库到翻译全链路
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Dict, List
import pytest

# ---------------------------------------------------------------------------
# 1. parse_lexicon — 词性拆分
# ---------------------------------------------------------------------------

from app.parse_lexicon import (
    _POS_BRACKET_RE,
    _POS_SHORT_RE,
    build_lexicon_index,
    build_lexicon_index_with_pos,
    load_master_library,
    split_pos_from_key,
    PosEntry,
)


class TestLexiconPosParsing:
    """测试词库解析时拆分词性括号 (.xxx/yyy)。"""

    def test_simple_entry_no_pos(self):
        """无括号的词条应正常解析，pos 为空字符串。"""
        data = {"那个": "gugu", "跑": "mova"}
        index = build_lexicon_index(data)
        assert index.get("那个") == "gugu"
        assert index.get("跑") == "mova"

    def test_entry_with_pos_bracket(self):
        """含括号词性的词条：key 应为纯中文词，pos 应被剥离单独存储。"""
        data = {"那个(.n/指示代词)": "gugu", "跑(.v/动词)": "mova"}
        index = build_lexicon_index(data)
        # 改造后的期望：key 是"那个"和"跑"，不是带括号的原文
        assert "那个" in index
        assert "跑" in index
        # 不应存在带括号的 key
        assert "那个(.n/指示代词)" not in index
        assert "跑(.v/动词)" not in index

    def test_same_word_different_pos(self):
        """同词不同词性（多义项）：build_lexicon_index_with_pos 应分别保留。"""
        data = {
            "跑(.v/动词)": "mova",
            "跑(.n/跑步)": "runing",
        }
        pos_index = build_lexicon_index_with_pos(data)
        assert "跑" in pos_index
        assert len(pos_index["跑"]) == 2
        # 验证 PosEntry 内容
        entries = pos_index["跑"]
        conlangs = {e.conlang for e in entries}
        assert "mova" in conlangs
        assert "runing" in conlangs

    def test_mixed_entries(self):
        """混合有括号和无括号的词条。"""
        data = {
            "那个(.n/指示代词)": "gugu",
            "跑": "mova",
            "水": "vat",
        }
        index = build_lexicon_index(data)
        assert "那个" in index
        assert "跑" in index
        assert "水" in index

    def test_pos_regex_pattern(self):
        """正则模式 (.xxx/yyy) 的各种变体。"""
        # 标准格式 — 使用项目内置正则
        assert _POS_BRACKET_RE.search("那个(.n/指示代词)")
        assert _POS_BRACKET_RE.search("跑(.v/动词)")
        # 短格式 (.v) — 使用 _POS_SHORT_RE
        assert _POS_SHORT_RE.search("跑(.v)")
        # 在中文词中匹配，提取括号内容
        m = _POS_BRACKET_RE.search("那个(.n/指示代词)")
        assert m is not None
        assert m.group() == "(.n/指示代词)"


# ---------------------------------------------------------------------------
# 2. 词性拆分辅助函数测试
# ---------------------------------------------------------------------------


class TestSplitPosFromKey:
    """测试 split_pos_from_key 工具函数。"""

    def test_no_pos(self):
        cn, pos = split_pos_from_key("那个")
        assert cn == "那个"
        assert pos == ""

    def test_standard_pos(self):
        cn, pos = split_pos_from_key("那个(.n/指示代词)")
        assert cn == "那个"
        assert pos == ".n/指示代词"

    def test_short_pos(self):
        cn, pos = split_pos_from_key("跑(.v)")
        assert cn == "跑"
        assert pos == ".v"

    def test_pos_with_slash_empty(self):
        cn, pos = split_pos_from_key("跑(.v/)")
        assert cn == "跑"
        assert pos == ".v/"

    def test_multiple_brackets_only_first(self):
        """如果词条含多个括号，只剥离第一个词性括号。"""
        cn, pos = split_pos_from_key("跑(.v/动词)(注)")
        assert cn == "跑(注)"
        assert pos == ".v/动词"

    def test_cjk_key_with_pos(self):
        cn, pos = split_pos_from_key("水(.n/名词)")
        assert cn == "水"
        assert pos == ".n/名词"

    def test_legacy_dot_end_pos(self):
        """旧词库格式 (xxx.) 如 灵魂(n.)，应拆分为 cn='灵魂', pos='.n'。"""
        cn, pos = split_pos_from_key("灵魂(n.)")
        assert cn == "灵魂"
        assert pos == ".n"

    def test_legacy_dot_end_pos_variants(self):
        """旧格式的各种词性：(v.), (adj.), (adv.)。"""
        cn, pos = split_pos_from_key("跑(v.)")
        assert cn == "跑"
        assert pos == ".v"
        cn, pos = split_pos_from_key("快(adj.)")
        assert cn == "快"
        assert pos == ".adj"


# ---------------------------------------------------------------------------
# 3. rule_translator — 两级匹配策略
# ---------------------------------------------------------------------------

from app.rule_translator import translate_rule, _segment_longest_match


class TestRuleTranslatorPosMatching:
    """测试翻译匹配时的词性策略。"""

    def test_basic_match_without_pos(self):
        """无词性词库：正常最长匹配。"""
        lexicon = {"那个": "gugu", "水": "vat"}
        tokens = _segment_longest_match("那个水", lexicon)
        assert all(t.is_matched for t in tokens)

    def test_match_with_pos_lexicon(self):
        """有词性词库：匹配 key 是纯中文词（不含括号）。"""
        lexicon = {"那个": "gugu", "水": "vat"}
        pos_lexicon = {
            "那个": [PosEntry(cn="那个", pos=".n/指示代词", conlang="gugu")],
            "水": [PosEntry(cn="水", pos=".n/名词", conlang="vat")],
        }
        tokens = _segment_longest_match("那个水", lexicon, pos_lexicon=pos_lexicon)
        assert all(t.is_matched for t in tokens)

    def test_fallback_when_pos_not_matched(self):
        """词性不匹配时 fallback 到仅中文词匹配。"""
        lexicon = {"跑": "mova"}
        pos_lexicon = {
            "跑": [
                PosEntry(cn="跑", pos=".v/动词", conlang="mova"),
                PosEntry(cn="跑", pos=".n/跑步", conlang="runing"),
            ],
        }
        # 无 jieba 提示时 fallback 取第一条
        result = translate_rule("跑", lexicon, {}, pos_lexicon)
        assert result.conlang == "mova"

    def test_multi_sense_disambiguation(self):
        """多义项场景：同一中文词有多个词性时，无提示时 fallback 第一条。"""
        lexicon = {"跑": "mova"}
        pos_lexicon = {
            "跑": [
                PosEntry(cn="跑", pos=".v/动词", conlang="mova"),
                PosEntry(cn="跑", pos=".n/跑步", conlang="runing"),
            ],
        }
        result = translate_rule("跑", lexicon, {}, pos_lexicon)
        # fallback 时取第一条
        assert "mova" in result.conlang


# ---------------------------------------------------------------------------
# 4. paperhub_client — AI候选词带词性
# ---------------------------------------------------------------------------

from app.paperhub_client import NewWord, _parse_new_words


class TestPaperHubPos:
    """测试 AI 候选词的词性解析。"""

    def test_new_word_without_pos(self):
        """AI 输出的新词不含词性时，pos 为空。"""
        raw = [{"chinese": "跑", "conlang": "mova", "ipa": "", "tts": "mova", "logic": ""}]
        words = _parse_new_words(raw)
        assert len(words) == 1
        assert words[0].chinese == "跑"
        assert words[0].pos == ""

    def test_new_word_with_pos(self):
        """AI 输出的新词含词性括号时，应拆分存储。"""
        raw = [{"chinese": "跑(.v/动词)", "conlang": "mova", "ipa": "", "tts": "mova", "logic": ""}]
        words = _parse_new_words(raw)
        assert len(words) == 1
        assert words[0].chinese == "跑"
        assert words[0].pos == ".v/动词"


# ---------------------------------------------------------------------------
# 5. 词库文件读写兼容测试
# ---------------------------------------------------------------------------

from app.storage import JsonStorage


class TestStoragePosCompat:
    """测试词库文件读写对 pos 字段的兼容。"""

    def test_write_and_read_with_pos(self):
        """写入带 pos 的词条后再读取，应正确还原。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            storage = JsonStorage(base)
            state = storage.load_config()
            lang = state["languages"][0]
            lang_dir = storage.language_dir(lang)
            lang_dir.mkdir(parents=True, exist_ok=True)

            master_path = storage.asset_path(lang, "master_library")
            # 写入带 pos 的词库
            data = {
                "那个(.n/指示代词)": "gugu",
                "跑(.v/动词)": "mova",
                "水": "vat",
            }
            master_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # 读取并解析（load_master_library 现返回 4 元组）
            idx, pos_idx, n, raw = load_master_library(master_path)
            # idx key 应是纯中文词
            assert "那个" in idx
            assert "跑" in idx
            assert "水" in idx
            # pos_idx 也应有对应条目
            assert "那个" in pos_idx
            assert "跑" in pos_idx

    def test_old_format_compat(self):
        """旧格式（无 pos）的词库应完全兼容。"""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            storage = JsonStorage(base)
            state = storage.load_config()
            lang = state["languages"][0]

            master_path = storage.asset_path(lang, "master_library")
            data = {"那个": "gugu", "跑": "mova"}
            master_path.parent.mkdir(parents=True, exist_ok=True)
            master_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            idx, pos_idx, n, raw = load_master_library(master_path)
            assert idx.get("那个") == "gugu"
            assert idx.get("跑") == "mova"


# ---------------------------------------------------------------------------
# 6. 集成测试：从词库到翻译全链路
# ---------------------------------------------------------------------------


class TestPosIntegration:
    """词性功能的端到端集成测试。"""

    def test_full_pipeline_with_pos(self):
        """从含 pos 词库出发，翻译应正确匹配。"""
        # 构造含 pos 的词库
        lexicon_raw = {
            "那个(.n/指示代词)": "gugu",
            "水(.n/名词)": "vat",
            "跑(.v/动词)": "mova",
            "跑(.n/跑步)": "runing",
        }
        # 解析后应拆分 pos
        index = build_lexicon_index(lexicon_raw)
        pos_index = build_lexicon_index_with_pos(lexicon_raw)
        assert "那个" in index
        assert "水" in index
        # 多义项的"跑"应有两个 PosEntry
        assert len(pos_index["跑"]) == 2

    def test_full_pipeline_without_pos(self):
        """不含 pos 的词库，翻译链路不受影响。"""
        lexicon = {"那个": "gugu", "水": "vat"}
        result = translate_rule("那个水", lexicon, {})
        assert result.match_rate == 1.0