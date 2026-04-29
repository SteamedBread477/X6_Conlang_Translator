"""Comprehensive test suite for Stage 9 modules."""
import sys
import os

# Activate venv if PyQt5 is not available
if "PyQt5" not in sys.modules:
    venv_path = os.path.join(os.path.dirname(__file__), "venv", "Scripts")
    if os.path.isdir(venv_path):
        site_packages = os.path.join(os.path.dirname(__file__), "venv", "Lib", "site-packages")
        if os.path.isdir(site_packages):
            sys.path.insert(0, site_packages)

import tempfile
import traceback

errors = []

def check(label, actual, expected):
    if actual != expected:
        errors.append(f"FAIL: {label} -- expected {expected}, got {actual}")
        print(f"  x {label}: expected {expected!r}, got {actual!r}")
    else:
        print(f"  v {label}")

# ── Test 1: ssml_generator utilities ──────────────────────────
from app.ssml_generator import (
    generate_ssml_tag,
    compute_prosody_attrs,
    ProsodyAttrs,
    _parse_pct,
    _format_pct,
    _add_pcts,
)

print("=" * 60)
print("1. _parse_pct / _format_pct / _add_pcts")
print("=" * 60)
check("parse +10%", _parse_pct("+10%"), 10.0)
check("parse -5%", _parse_pct("-5%"), -5.0)
check("parse empty", _parse_pct(""), 0.0)
check("parse 0%", _parse_pct("0%"), 0.0)
check("format 10", _format_pct(10.0), "+10%")
check("format -20", _format_pct(-20.0), "-20%")
check("format 0", _format_pct(0.0), "")
check("add -10% + -10%", _add_pcts("-10%", "-10%"), "-20%")
check("add +10% + -5%", _add_pcts("+10%", "-5%"), "+5%")
check("add '' + -10%", _add_pcts("", "-10%"), "-10%")
check("add '' + ''", _add_pcts("", ""), "")

# ── Test 2: base emotions ─────────────────────────────────────
print()
print("=" * 60)
print("2. compute_prosody_attrs -- base emotions")
print("=" * 60)
tests = {
    "Sad":    ("slow", "-10%", ""),
    "Happy":  ("fast", "+10%", ""),
    "Urgent": ("fast", "",     "loud"),
    "Calm":   ("medium", "",   ""),
    "Angry":  ("fast", "+5%",  "loud"),
    "Fear":   ("slow", "+5%",  ""),
    "Neutral":("medium", "",   ""),
}
for emotion, (er, ep, ev) in tests.items():
    p = compute_prosody_attrs(emotion, "Normal", "Middle")
    check(f"{emotion} rate", p.rate, er)
    check(f"{emotion} pitch", p.pitch, ep)
    check(f"{emotion} volume", p.volume, ev)

# ── Test 3: body type overlay ─────────────────────────────────
print()
print("=" * 60)
print("3. compute_prosody_attrs -- body type pitch overlay")
print("=" * 60)
p = compute_prosody_attrs("Sad", "Strong", "Middle")
check("Sad+Strong pitch", p.pitch, "-15%")
check("Sad+Strong rate", p.rate, "slow")

p = compute_prosody_attrs("Sad", "Heavy", "Middle")
check("Sad+Heavy pitch", p.pitch, "-20%")

# ── Test 4: age rate adjustment ────────────────────────────────
print()
print("=" * 60)
print("4. compute_prosody_attrs -- age rate adjustment")
print("=" * 60)
p = compute_prosody_attrs("Sad", "Normal", "Old")
check("Sad+Old rate", p.rate, "x-slow")

p = compute_prosody_attrs("Sad", "Normal", "Young")
check("Sad+Young rate", p.rate, "medium")

p = compute_prosody_attrs("Happy", "Normal", "Old")
check("Happy+Old rate", p.rate, "medium")

p = compute_prosody_attrs("Happy", "Normal", "Young")
check("Happy+Young rate", p.rate, "x-fast")

p = compute_prosody_attrs("Calm", "Normal", "Young")
check("Calm+Young rate", p.rate, "fast")

p = compute_prosody_attrs("Calm", "Normal", "Old")
check("Calm+Old rate", p.rate, "slow")

# ── Test 5: combined spec example ──────────────────────────────
print()
print("=" * 60)
print("5. compute_prosody_attrs -- combined (spec example)")
print("=" * 60)
p = compute_prosody_attrs("Sad", "Heavy", "Old")
check("Sad+Heavy+Old pitch", p.pitch, "-20%")
check("Sad+Heavy+Old rate", p.rate, "x-slow")
check("Sad+Heavy+Old volume", p.volume, "")

# ── Test 6: generate_ssml_tag ──────────────────────────────────
print()
print("=" * 60)
print("6. generate_ssml_tag -- full output")
print("=" * 60)
tag = generate_ssml_tag("Sad", "Heavy", "Old", "kuthara lomae")
expected_lines = [
    "<speak>",
    '<prosody rate="x-slow" pitch="-20%">',
    "kuthara lomae",
    "</prosody>",
    "</speak>",
]
expected_tag = "\n".join(expected_lines)
check("Sad+Heavy+Old SSML", tag, expected_tag)

tag_empty = generate_ssml_tag("Neutral", "Normal", "Middle", "")
expected_empty = "<speak>\n\n</speak>"
check("Neutral+empty tts SSML", tag_empty, expected_empty)

tag_urgent = generate_ssml_tag("Urgent", "Normal", "Middle", "test")
check("Urgent SSML has volume", "volume=\"loud\"" in tag_urgent, True)

# ── Test 7: edge cases ──────────────────────────────────────────
print()
print("=" * 60)
print("7. Edge cases -- unknown emotion, empty inputs, case")
print("=" * 60)
p = compute_prosody_attrs("UnknownEmotion", "Normal", "Middle")
check("Unknown emotion -> Neutral rate", p.rate, "medium")
check("Unknown emotion -> Neutral pitch", p.pitch, "")

p = compute_prosody_attrs("", "", "")
check("Empty -> Neutral rate", p.rate, "medium")
check("Empty -> Normal pitch", p.pitch, "")

p = compute_prosody_attrs("sad", "heavy", "old")
check("Lowercase sad -> Sad pitch", p.pitch, "-20%")

p = compute_prosody_attrs("HAPPY", "NORMAL", "YOUNG")
check("Uppercase HAPPY -> x-fast rate", p.rate, "x-fast")

# ── Test 8: BatchTranslateResult fields ──────────────────────────
print()
print("=" * 60)
print("8. BatchTranslateResult dataclass")
print("=" * 60)
from app.batch_translator import BatchTranslateResult
r = BatchTranslateResult()
check("ssml_tag field exists", hasattr(r, "ssml_tag"), True)
check("body_type field exists", hasattr(r, "body_type"), True)
check("age field exists", hasattr(r, "age"), True)
check("default ssml_tag", r.ssml_tag, "")
check("default body_type", r.body_type, "")
check("default age", r.age, "")

# ── Test 9: BatchTranslateWorker attributes ────────────────────────
print()
print("=" * 60)
print("9. BatchTranslateWorker pause/resume/cancel")
print("=" * 60)
from app.batch_translate_dialog import BatchTranslateSettings
from app.batch_translator import BatchTranslateWorker
settings = BatchTranslateSettings()
worker = BatchTranslateWorker([], settings, {}, {})
check("is_paused initially False", worker.is_paused, False)
check("_MAX_RETRIES=3", worker._MAX_RETRIES, 3)
check("_RETRY_BASE_DELAY=2.0", worker._RETRY_BASE_DELAY, 2.0)

worker.pause()
check("paused after pause()", worker.is_paused, True)
worker.resume()
check("unpaused after resume()", worker.is_paused, False)

worker.pause()
worker.cancel()
check("cancel clears pause", worker.is_paused, False)
check("cancelled after cancel()", worker._cancelled, True)

# ── Test 10: PaperHubError status_code ─────────────────────────────
print()
print("=" * 60)
print("10. PaperHubError status_code")
print("=" * 60)
from app.paperhub_client import PaperHubError
e1 = PaperHubError("test", user_hint="hint")
check("default status_code=0", e1.status_code, 0)
e2 = PaperHubError("rate limited", user_hint="限流", status_code=429)
check("status_code=429", e2.status_code, 429)
check("user_hint preserved", e2.user_hint, "限流")

# ── Test 11: export_results_to_excel columns ────────────────────────
print()
print("=" * 60)
print("11. export_results_to_excel column names and values")
print("=" * 60)
from app.batch_translator import export_results_to_excel
from app.excel_import import ExcelRow

ssml_test = generate_ssml_tag("Sad", "Heavy", "Old", "ku.tha.ra")
results = [
    BatchTranslateResult(
        row_index=0, row_id="ID1", emotion="Sad",
        body_type="Heavy", age="Old",
        chinese_text="你好", conlang="kuthara", tts="ku.tha.ra",
        ssml_tag=ssml_test,
        mode_used="rule",
    ),
]
original_rows = [ExcelRow(data={
    "台本ID": "ID1", "Text": "你好",
    "Emotion": "Sad", "Body_Type": "Heavy", "Age": "Old",
})]

tmp_dir = tempfile.mkdtemp()
output_path = os.path.join(tmp_dir, "test_output.xlsx")
success = export_results_to_excel(results, original_rows, output_path)
check("export succeeds", success, True)

if success:
    try:
        import pandas as pd
        df = pd.read_excel(output_path)
        cols = list(df.columns)
        check("Conlang_Text column", "Conlang_Text" in cols, True)
        check("TTS_Phonetic column", "TTS_Phonetic" in cols, True)
        check("SSML_Tag column", "SSML_Tag" in cols, True)
        check("Conlang_Text value", df["Conlang_Text"].iloc[0], "kuthara")
        check("TTS_Phonetic value", df["TTS_Phonetic"].iloc[0], "ku.tha.ra")
        check("SSML_Tag contains <speak>", "<speak>" in str(df["SSML_Tag"].iloc[0]), True)
        check("Old Conlang col removed", "Conlang" not in cols, True)
        check("Old TTS col removed", "TTS" not in cols, True)
    except ImportError:
        print("  ! pandas not available, skipping column content check")
    try:
        os.remove(output_path)
        os.rmdir(tmp_dir)
    except Exception:
        pass

# ── Test 12: main_window button references ──────────────────────────
print()
print("=" * 60)
print("12. main_window batch buttons (code inspection)")
print("=" * 60)
# Verify the button references exist in the code
import inspect
from app.main_window import MainWindow
source = inspect.getsource(MainWindow)
check("_btn_batch_start in source", "_btn_batch_start" in source, True)
check("_btn_batch_pause in source", "_btn_batch_pause" in source, True)
check("_btn_batch_cancel in source", "_btn_batch_cancel" in source, True)
check("_on_batch_log method", "_on_batch_log" in source, True)
check("_on_batch_pause_resume method", "_on_batch_pause_resume" in source, True)
check("_on_batch_cancel method", "_on_batch_cancel" in source, True)

# ── Test 13: Worker log_message signal ──────────────────────────────
print()
print("=" * 60)
print("13. BatchTranslateWorker log_message signal")
print("=" * 60)
from PyQt5.QtCore import pyqtSignal
# Check signal exists
check("log_message signal exists", hasattr(BatchTranslateWorker, "log_message"), True)

# ── Final summary ────────────────────────────────────────────────────
print()
print("=" * 60)
if errors:
    print(f"RESULT: {len(errors)} FAILURES")
    for e in errors:
        print(f"  {e}")
else:
    print("RESULT: ALL TESTS PASSED v")
print("=" * 60)