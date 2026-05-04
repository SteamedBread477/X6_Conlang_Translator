"""语言大师候选词的数据模型 + 存储。

之前候选词数据"住"在 QTableWidget 的 cell 字符串里：
  - 读取靠 self._ask_pending_table.item(row, col).text().strip()，6 处重复
  - 写入靠 setItem，markdown 装饰（**lumi**）剥��逻辑只在 parse 处做了一次
  - 加字段 = 加列 + 改读 + 改写，几处不同步会产生脏数据（已被 *style* 标签
    那次以及 **lumi** 那次咬过）

本模型把数据从 view 中抽出：
  - PendingWord：候选词的结构化记录（conlang/ipa/tts/meaning/style）
  - PendingWord.from_ai_match：唯一的 AI 输出清洗入口（剥 markdown / 反引号 /
    斜体下划线）；表格创建时强制走它，view 拿到的就是干净的字符串
  - PendingWordStore：存活在 MainWindow 上的 source-of-truth，QTableWidget
    退化为纯展示（每次变更后由 store.as_view_rows 重渲染）

未来加字段：
  - �� PendingWord 加新字段
  - 在 from_ai_match 决定如何从 AI 文本提取
  - 在 view 渲染逻辑加列
  读路径自动同步，不用再追着 6 个 cell.text() 改。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Iterator, List, Optional, Tuple


# ---------------------------------------------------------------------------
# AI 输出装饰剥离（与 main_window._ask_parse_ai_response 内的 _clean 等价）
# ---------------------------------------------------------------------------

def strip_markdown_decoration(s: str) -> str:
    """剥离 AI 字段中常见的 markdown 装饰（加粗/斜体/反引号/下划线）。

    - 反复剥离成对的 *、**、***、_、__、___、`、`` 包裹（最多 3 轮）
    - 兜底 strip 残余的孤立 *、`、_（处理不闭合）
    - 内部 * 不动（如 a*b），仅作用于首尾
    """
    s = (s or "").strip()
    for _ in range(3):
        stripped = re.sub(r"^(\*{1,3}|`+|_{1,3})(.+?)\1$", r"\2", s)
        if stripped == s:
            break
        s = stripped.strip()
    s = s.strip("*`_ \t")
    return s


# ---------------------------------------------------------------------------
# 候选词数据模型
# ---------------------------------------------------------------------------

@dataclass
class PendingWord:
    """语言大师候选词的结构化记录。

    字段对应表格列：自创语 / IPA / TTS / 含义 / 风格标签
    所有字段保证已剥离 AI 输出装饰（来自 from_ai_match 工厂）。
    """
    conlang: str
    ipa: str = ""
    tts: str = ""
    meaning: str = ""  # 表格"含义"列：候选词的中文意思（写进词库时是 zh-key）
    style: str = ""    # 表格"风格标签"列：词条风格元数据（写进 lexicon_meta.style）

    @classmethod
    def from_ai_match(
        cls,
        conlang: str,
        ipa: str,
        tts: str,
        meaning: str,
        tags: str,
    ) -> "PendingWord":
        """工厂：从 AI【新词】行的 5 个原始捕获组构造，统一剥 markdown。"""
        return cls(
            conlang=strip_markdown_decoration(conlang),
            ipa=strip_markdown_decoration(ipa),
            tts=strip_markdown_decoration(tts),
            meaning=strip_markdown_decoration(meaning),
            style=strip_markdown_decoration(tags),
        )

    @property
    def is_valid(self) -> bool:
        """是否可以入库。中文 + 自创语必填。"""
        return bool(self.meaning.strip()) and bool(self.conlang.strip())

    def label(self) -> str:
        """供 system 消息使用的人类可读标签，如 '光 → lumi'。"""
        return f"{self.meaning} → {self.conlang}"

    def to_view_row(self) -> Tuple[str, str, str, str, str]:
        """渲染到 QTableWidget 的 5 列文本（不含操作列）。"""
        return (self.conlang, self.ipa, self.tts, self.meaning, self.style)


# ---------------------------------------------------------------------------
# Store：source of truth
# ---------------------------------------------------------------------------

class PendingWordStore:
    """候选词集合的存储。

    - 顺序就是 UI 表格行顺序
    - 索引 == 行号；删除会触发后续行号偏移，调用方在 view 重渲染时按 store
      重建按钮 lambda 即可（不再依赖捕获时的 row 号）
    - 不主动通知；view 在每次 mutation 后自己重建表格内容
    """

    def __init__(self) -> None:
        self._words: List[PendingWord] = []

    # ---- 查询 ----

    def __len__(self) -> int:
        return len(self._words)

    def __iter__(self) -> Iterator[PendingWord]:
        return iter(self._words)

    def __getitem__(self, index: int) -> PendingWord:
        return self._words[index]

    def is_empty(self) -> bool:
        return not self._words

    def all(self) -> List[PendingWord]:
        return list(self._words)

    def view_rows(self) -> List[Tuple[str, str, str, str, str]]:
        return [w.to_view_row() for w in self._words]

    def get(self, index: int) -> Optional[PendingWord]:
        if 0 <= index < len(self._words):
            return self._words[index]
        return None

    def valid_words(self) -> List[PendingWord]:
        """返回所有 is_valid 的候选词（用于批量入库前的过滤）。"""
        return [w for w in self._words if w.is_valid]

    # ---- 修改 ----

    def add(self, word: PendingWord) -> None:
        self._words.append(word)

    def add_from_ai_match(
        self, conlang: str, ipa: str, tts: str, meaning: str, tags: str
    ) -> PendingWord:
        """便捷入口：构造 + 入 store。返回构造好的对象供调用方使用。"""
        w = PendingWord.from_ai_match(conlang, ipa, tts, meaning, tags)
        self._words.append(w)
        return w

    def extend(self, words: Iterable[PendingWord]) -> None:
        self._words.extend(words)

    def remove_at(self, index: int) -> Optional[PendingWord]:
        """按索引删除，返回被删的对象（供 system 消息用）。索引越界返回 None。"""
        if 0 <= index < len(self._words):
            return self._words.pop(index)
        return None

    def remove_indices(self, indices: Iterable[int]) -> List[PendingWord]:
        """批量删除（如多选确认/丢弃后）。返回被删的对象列表（按原顺序）。"""
        # 倒序删除以保持索引有效；返回时按升序原索引顺序
        sorted_idx = sorted({i for i in indices if 0 <= i < len(self._words)})
        removed: List[PendingWord] = [self._words[i] for i in sorted_idx]
        for i in sorted(sorted_idx, reverse=True):
            del self._words[i]
        return removed

    def clear(self) -> None:
        self._words.clear()
