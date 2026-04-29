"""
SSML 语音标签生成模块（阶段九）。

根据 Excel 台本中的 Emotion / Body_Type / Age 字段，
生成 TTS 引擎可用的 SSML <prosody> 标签。

映射规则（叠加计算）：
  ┌─────────┬──────────────────────────────────────┐
  │ Emotion │ SSML 配置                             │
  ├─────────┼──────────────────────────────────────┤
  │ Sad     │ rate="slow" pitch="-10%"              │
  │ Happy   │ rate="fast" pitch="+10%"              │
  │ Urgent  │ rate="fast" volume="loud"             │
  │ Calm    │ rate="medium"                         │
  │ Angry   │ rate="fast" pitch="+5%" volume="loud" │
  │ Fear    │ rate="slow" pitch="+5%"               │
  │ Neutral │ rate="medium"                         │
  └─────────┴──────────────────────────────────────┘

  ┌───────────┬────────────────┐
  │ Body_Type │ Pitch 调整     │
  ├───────────┼────────────────┤
  │ Normal    │ 不调整         │
  │ Strong    │ pitch 再 -5%   │
  │ Heavy     │ pitch 再 -10%  │
  └───────────┴────────────────┘

  ┌───────┬─────────────┐
  │ Age   │ Rate 调整   │
  ├───────┼─────────────┤
  │ Young │ rate +10%   │
  │ Middle│ 不调整      │
  │ Old   │ rate -10%   │
  └───────┴─────────────┘

最终 pitch = emotion_pitch + body_type_pitch（代数叠加）
最终 rate  由 emotion_rate 和 age_rate 共同决定：
  - emotion_rate 为字面值时（slow/fast/medium），按 age 微调
  - emotion_rate 为百分比时，与 age 百分比代数叠加

公开接口：
  generate_ssml_tag(emotion, body_type, age, tts_phonetic) -> str
  compute_prosody_attrs(emotion, body_type, age) -> ProsodyAttrs
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


# ---------------------------------------------------------------------------
# 情绪映射表
# ---------------------------------------------------------------------------

# 每个 emotion -> (rate_literal_or_pct, pitch_pct, volume)
# rate: 字面值 "slow"/"fast"/"medium" 或百分比如 "+10%"
# pitch: 百分比字符串如 "-10%" / "+10%" 或空 ""
# volume: "loud" / "soft" / ""（空=不设）
EMOTION_MAP: Dict[str, Tuple[str, str, str]] = {
    "Sad":    ("slow",   "-10%", ""),
    "Happy":  ("fast",   "+10%", ""),
    "Urgent": ("fast",   "",     "loud"),
    "Calm":   ("medium", "",     ""),
    "Angry":  ("fast",   "+5%",  "loud"),
    "Fear":   ("slow",   "+5%",  ""),
    "Neutral":("medium", "",     ""),
}

# ---------------------------------------------------------------------------
# 体型调整表
# ---------------------------------------------------------------------------

# Body_Type -> pitch 百分比调整（叠加到 emotion pitch）
BODY_TYPE_PITCH: Dict[str, str] = {
    "Normal": "",
    "Strong": "-5%",
    "Heavy":  "-10%",
}

# ---------------------------------------------------------------------------
# Age 调整表
# ---------------------------------------------------------------------------

# 当 emotion_rate 为字面值时，用此映射表微调：
#   (emotion_rate, age) -> final_rate
AGE_RATE_ADJUST: Dict[Tuple[str, str], str] = {
    # slow 组
    ("slow",   "Old"):   "x-slow",
    ("slow",   "Middle"): "slow",
    ("slow",   "Young"):  "medium",
    # fast 组
    ("fast",   "Old"):    "medium",
    ("fast",   "Middle"): "fast",
    ("fast",   "Young"):  "x-fast",
    # medium 组
    ("medium", "Old"):    "slow",
    ("medium", "Middle"): "medium",
    ("medium", "Young"):  "fast",
}


# ---------------------------------------------------------------------------
# 辅助：百分比代数运算
# ---------------------------------------------------------------------------

def _parse_pct(pct_str: str) -> float:
    """将百分比字符串解析为浮点数。'+10%' -> 10.0, '-5%' -> -5.0, '' -> 0.0"""
    if not pct_str:
        return 0.0
    s = pct_str.strip().replace("%", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _format_pct(value: float) -> str:
    """将浮点数格式化为百分比字符串。10.0 -> '+10%', -20.0 -> '-20%', 0.0 -> ''"""
    if value == 0.0:
        return ""
    sign = "+" if value > 0 else ""
    rounded = round(value)
    return f"{sign}{rounded}%"


def _add_pcts(a: str, b: str) -> str:
    """两个百分比字符串代数叠加。'-10%' + '-10%' -> '-20%'"""
    return _format_pct(_parse_pct(a) + _parse_pct(b))


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class ProsodyAttrs:
    """计算后的 SSML <prosody> 属性。"""
    rate: str = ""       # 字面值 "slow"/"fast"/"medium" 或百分比 "+10%"
    pitch: str = ""      # 百分比 "-10%" / "+5%" 等
    volume: str = ""     # "loud" / "soft" / ""


# ---------------------------------------------------------------------------
# 核心计算
# ---------------------------------------------------------------------------

def compute_prosody_attrs(
    emotion: str,
    body_type: str = "Normal",
    age: str = "Middle",
) -> ProsodyAttrs:
    """
    根据 Emotion / Body_Type / Age 计算 SSML <prosody> 属性。

    算法：
      1. 从 EMOTION_MAP 取基础 rate / pitch / volume
      2. 从 BODY_TYPE_PITCH 取 pitch 调整，叠加到基础 pitch
      3. 根据 age 微调 rate：
         - 若基础 rate 为字面值（slow/fast/medium），查 AGE_RATE_ADJUST 表
         - 若基础 rate 为百分比，与 age 百分比代数叠加
    """
    emotion = (emotion or "Neutral").strip().capitalize()
    body_type = (body_type or "Normal").strip().capitalize()
    age = (age or "Middle").strip().capitalize()

    # Step 1: 情绪基础值
    base_rate, base_pitch, base_volume = EMOTION_MAP.get(
        emotion, EMOTION_MAP["Neutral"]
    )

    # Step 2: 体型 pitch 调整叠加
    body_pitch = BODY_TYPE_PITCH.get(body_type, "")
    final_pitch = _add_pcts(base_pitch, body_pitch)

    # Step 3: Age rate 调整
    final_rate = base_rate
    age_pct_map = {"Young": "+10%", "Old": "-10%", "Middle": ""}

    if base_rate in ("slow", "fast", "medium"):
        key = (base_rate, age)
        final_rate = AGE_RATE_ADJUST.get(key, base_rate)
    else:
        age_rate_pct = age_pct_map.get(age, "")
        final_rate = _add_pcts(base_rate, age_rate_pct)
        if not final_rate:
            final_rate = "medium"

    return ProsodyAttrs(rate=final_rate, pitch=final_pitch, volume=base_volume)


# ---------------------------------------------------------------------------
# SSML 标签生成
# ---------------------------------------------------------------------------

def generate_ssml_tag(
    emotion: str,
    body_type: str = "Normal",
    age: str = "Middle",
    tts_phonetic: str = "",
) -> str:
    """
    生成完整的 SSML <speak> 标签。

    示例：
      emotion=Sad, body_type=Heavy, age=Old, tts_phonetic="kuthara lomae"
      ->
      <speak>
      <prosody rate="x-slow" pitch="-20%">
      kuthara lomae
      </prosody>
      </speak>
    """
    attrs = compute_prosody_attrs(emotion, body_type, age)

    # rate="medium" is the TTS default — equivalent to no adjustment.
    # Only include it when there are other meaningful attributes alongside it.
    attr_parts = []
    if attrs.rate and attrs.rate != "medium":
        attr_parts.append('rate="' + attrs.rate + '"')
    if attrs.pitch:
        attr_parts.append('pitch="' + attrs.pitch + '"')
    if attrs.volume:
        attr_parts.append('volume="' + attrs.volume + '"')

    # If all we have is rate="medium" (no-op), don't generate <prosody>.
    # But if there's pitch or volume alongside rate="medium", keep it.
    if attrs.rate == "medium" and (attrs.pitch or attrs.volume):
        attr_parts.append('rate="medium"')

    attr_str = " " + " ".join(attr_parts) if attr_parts else ""
    content = tts_phonetic or ""

    if attr_str:
        lines = [
            "<speak>",
            "<prosody" + attr_str + ">",
            content,
            "</prosody>",
            "</speak>",
        ]
        return "\n".join(lines)
    else:
        return "<speak>\n" + content + "\n</speak>"