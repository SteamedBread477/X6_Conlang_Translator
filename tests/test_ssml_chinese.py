"""测试 SSML 生成模块的中文输入规范化。"""
import pytest
from app.ssml_generator import compute_prosody_attrs, generate_ssml_tag


class TestEmotionNormalization:
    """中文情绪 → 英文 key 映射。"""

    def test_calm_chinese(self):
        # 慈祥 → Calm → rate=medium
        attrs = compute_prosody_attrs("慈祥", "正常", "中年")
        assert attrs.rate == "medium"

    def test_angry_chinese(self):
        # 威严 → Angry → rate=fast, volume=loud
        attrs = compute_prosody_attrs("威严", "正常", "中年")
        assert attrs.rate == "fast"
        assert attrs.volume == "loud"

    def test_happy_chinese(self):
        # 开心 → Happy → rate=fast, pitch=+10%
        attrs = compute_prosody_attrs("开心", "正常", "中年")
        assert attrs.rate == "fast"
        assert attrs.pitch == "+10%"

    def test_fear_chinese(self):
        # 恐惧 → Fear → rate=slow, pitch=+5%
        attrs = compute_prosody_attrs("恐惧", "正常", "青年")
        assert attrs.rate == "medium"
        assert attrs.pitch == "+5%"

    def test_sad_chinese(self):
        # 悲伤 → Sad → rate=slow, pitch=-10%
        attrs = compute_prosody_attrs("悲伤", "正常", "中年")
        assert attrs.rate == "slow"
        assert attrs.pitch == "-10%"

    def test_urgent_chinese(self):
        # 紧急 → Urgent → rate=fast, volume=loud
        attrs = compute_prosody_attrs("紧急", "正常", "中年")
        assert attrs.rate == "fast"
        assert attrs.volume == "loud"

    def test_unknown_emotion_fallback(self):
        # 不认识的中文 → fallback Neutral → rate=medium
        attrs = compute_prosody_attrs("疑惑", "正常", "中年")
        assert attrs.rate == "medium"

    def test_english_still_works(self):
        # 英文值不受影响
        attrs = compute_prosody_attrs("Sad", "Heavy", "Old")
        assert attrs.rate == "x-slow"
        assert attrs.pitch == "-20%"


class TestBodyTypeNormalization:
    """中文体型 → 英文 key 映射。"""

    def test_strong_chinese(self):
        # 魁梧 → Strong → pitch -5%
        attrs = compute_prosody_attrs("中性", "魁梧", "中年")
        assert attrs.pitch == "-5%"

    def test_heavy_chinese(self):
        # 矮小圆润 → Heavy → pitch -10%
        attrs = compute_prosody_attrs("中性", "矮小圆润", "中年")
        assert attrs.pitch == "-10%"

    def test_normal_chinese(self):
        # 正常 → Normal → 无调整
        attrs = compute_prosody_attrs("中性", "正常", "中年")
        assert attrs.pitch == ""


class TestAgeNormalization:
    """中文年龄 → 英文 key 映射。"""

    def test_old_chinese(self):
        # 老年 → Old → slow→x-slow
        attrs = compute_prosody_attrs("悲伤", "正常", "老年")
        assert attrs.rate == "x-slow"

    def test_young_chinese(self):
        # 青年 → Young → fast→x-fast
        attrs = compute_prosody_attrs("开心", "正常", "青年")
        assert attrs.rate == "x-fast"

    def test_middle_chinese(self):
        # 中年 → Middle → 不调整
        attrs = compute_prosody_attrs("平静", "正常", "中年")
        assert attrs.rate == "medium"


class TestSSMLTagGenerationChinese:
    """中文输入生成完整 SSML 标签。"""

    def test_full_chinese_tag(self):
        tag = generate_ssml_tag("慈祥", "矮小圆润", "老年", "kuthara lomae")
        assert "<speak>" in tag
        assert "<prosody" in tag
        assert "kuthara lomae" in tag

    def test_chinese_with_empty_phonetic(self):
        tag = generate_ssml_tag("威严", "高大魁梧", "中年", "")
        assert "<speak>" in tag
        assert 'volume="loud"' in tag