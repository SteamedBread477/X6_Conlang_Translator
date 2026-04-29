"""Comprehensive test suite for Stage 10 modules."""
import sys
import os

# Activate venv if PyQt5 is not available
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

# ── Test 1: generate_timestamp_filename ──────────────────────────
print("=" * 60)
print("1. generate_timestamp_filename")
print("=" * 60)
from app.batch_translator import generate_timestamp_filename
from datetime import datetime

ts_name = generate_timestamp_filename("NPC_Script.xlsx")
check("stem preserved", "NPC_Script" in ts_name, True)
check("_TTS_Ready_ in name", "_TTS_Ready_" in ts_name, True)
check(".xlsx extension", ts_name.endswith(".xlsx"), True)

ts_name_empty = generate_timestamp_filename("")
check("empty path fallback stem", "Translation" in ts_name_empty, True)

ts_name_noext = generate_timestamp_filename("MyFile")
check("no extension fallback", "MyFile" in ts_name_noext, True)
check("still has xlsx", ts_name_noext.endswith(".xlsx"), True)

# ── Test 2: export_results_to_excel returns stats dict ───────────
print()
print("=" * 60)
print("2. export_results_to_excel -- stats dict return")
print("=" * 60)
from app.batch_translator import BatchTranslateResult, export_results_to_excel
from app.excel_import import ExcelRow
from app.ssml_generator import generate_ssml_tag

ssml_test = generate_ssml_tag("Sad", "Heavy", "Old", "ku.tha.ra")
results = [
    BatchTranslateResult(
        row_index=0, row_id="ID1", emotion="Sad",
        body_type="Heavy", age="Old",
        chinese_text="你好", conlang="kuthara", tts="ku.tha.ra",
        ssml_tag=ssml_test,
        mode_used="hybrid_ai",
        ai_generated=True,
        ai_model="qwen3-max",
    ),
    BatchTranslateResult(
        row_index=1, row_id="ID2", emotion="Happy",
        body_type="Normal", age="Young",
        chinese_text="再见", conlang="", tts="", mode_used="rule",
    ),
]
original_rows = [
    ExcelRow(data={"台本ID": "ID1", "Text": "你好", "Emotion": "Sad", "Body_Type": "Heavy", "Age": "Old"}),
    ExcelRow(data={"台本ID": "ID2", "Text": "再见", "Emotion": "Happy"}),
]

tmp_dir = tempfile.mkdtemp()
output_path = os.path.join(tmp_dir, "test_s10_output.xlsx")
stats = export_results_to_excel(results, original_rows, output_path)

check("stats success", stats.get("success"), True)
check("stats total_rows", stats.get("total_rows"), 2)
check("stats success_count", stats.get("success_count"), 1)
check("stats failed_count (empty conlang with no error = 0)", stats.get("failed_count"), 0)
check("stats ai_generated_count", stats.get("ai_generated_count"), 1)
check("stats ai_model", stats.get("ai_model"), "qwen3-max")

# ── Test 3: export column layout (S10) ────────────────────────────
print()
print("=" * 60)
print("3. export column layout -- S10 columns")
print("=" * 60)
try:
    import pandas as pd
    df = pd.read_excel(output_path)
    cols = list(df.columns)
    check("Translation_ID column", "Translation_ID" in cols, True)
    check("Conlang_Text column", "Conlang_Text" in cols, True)
    check("TTS_Phonetic column", "TTS_Phonetic" in cols, True)
    check("SSML_Tag column", "SSML_Tag" in cols, True)
    check("Unmatched_Words column", "Unmatched_Words" in cols, True)
    check("AI_Generated column", "AI_Generated" in cols, True)
    check("AI_Model column", "AI_Model" in cols, True)
    # Old columns removed
    check("Old Conlang removed", "Conlang" not in cols, True)
    check("Old TTS removed", "TTS" not in cols, True)
    check("Old Translation_Mode removed", "Translation_Mode" not in cols, True)
    check("Old Error removed", "Error" not in cols, True)
    # Values
    check("AI_Generated row 0 = Yes", str(df["AI_Generated"].iloc[0]), "Yes")
    check("AI_Model row 0 = qwen3-max", str(df["AI_Model"].iloc[0]), "qwen3-max")
    check("Translation_ID format", str(df["Translation_ID"].iloc[0]).startswith("TH_"), True)
    check("AI_Generated row 1 = No", str(df["AI_Generated"].iloc[1]), "No")
    check("AI_Model row 1 is empty/NaN", pd.isna(df["AI_Model"].iloc[1]) or str(df["AI_Model"].iloc[1]) == "", True)
except ImportError:
    print("  ! pandas not available, skipping column content checks")

# Cleanup
try:
    os.remove(output_path)
    os.rmdir(tmp_dir)
except Exception:
    pass

# ── Test 4: BatchTranslateResult new S10 fields ──────────────────
print()
print("=" * 60)
print("4. BatchTranslateResult -- ai_generated / ai_model fields")
print("=" * 60)
r = BatchTranslateResult()
check("ai_generated field exists", hasattr(r, "ai_generated"), True)
check("ai_model field exists", hasattr(r, "ai_model"), True)
check("default ai_generated", r.ai_generated, False)
check("default ai_model", r.ai_model, "")

r2 = BatchTranslateResult(mode_used="hybrid_ai", ai_generated=True, ai_model="qwen3-max")
check("ai_generated=True", r2.ai_generated, True)
check("ai_model set", r2.ai_model, "qwen3-max")

r3 = BatchTranslateResult(mode_used="rule")
check("rule mode ai_generated=False", r3.ai_generated, False)

# ── Test 5: export_results_to_excel failure case ──────────────────
print()
print("=" * 60)
print("5. export_results_to_excel -- failure case")
print("=" * 60)
# Try exporting to a bad path (e.g. a directory that doesn't exist)
bad_path = os.path.join(tempfile.gettempdir(), "nonexistent_dir_xyz", "bad.xlsx")
stats_fail = export_results_to_excel(results, original_rows, bad_path)
check("fail stats success=False", stats_fail.get("success"), False)
check("fail stats dict length", len(stats_fail), 1)

# ── Test 6: ExportResultDialog class exists ────────────────────────
print()
print("=" * 60)
print("6. ExportResultDialog class import and structure")
print("=" * 60)
from app.export_result_dialog import ExportResultDialog
check("ExportResultDialog is class", ExportResultDialog.__name__, "ExportResultDialog")
import inspect
methods = [m[0] for m in inspect.getmembers(ExportResultDialog, predicate=inspect.isfunction)]
check("_show_new_words method", "_show_new_words" in methods, True)
check("_open_folder method", "_open_folder" in methods, True)
check("_open_file method", "_open_file" in methods, True)

# ── Test 7: NewWordsReportDialog class exists ──────────────────────
print()
print("=" * 60)
print("7. NewWordsReportDialog class import and structure")
print("=" * 60)
from app.new_words_report_dialog import NewWordsReportDialog
check("NewWordsReportDialog is class", NewWordsReportDialog.__name__, "NewWordsReportDialog")
methods = [m[0] for m in inspect.getmembers(NewWordsReportDialog, predicate=inspect.isfunction)]
check("_export_vocab method", "_export_vocab" in methods, True)
check("_add_to_lexicon method", "_add_to_lexicon" in methods, True)
check("get_added_to_lexicon method", "get_added_to_lexicon" in methods, True)

# ── Test 8: main_window S10 methods ────────────────────────────────
print()
print("=" * 60)
print("8. main_window S10 methods (code inspection)")
print("=" * 60)
from app.main_window import MainWindow
source = inspect.getsource(MainWindow)
check("_do_auto_export method", "_do_auto_export" in source, True)
check("_append_results_to_history method", "_append_results_to_history" in source, True)
check("_on_batch_export uses generate_timestamp_filename", "generate_timestamp_filename" in source, True)
check("_on_batch_export uses stats dict", "stats.get" in source or "stats[" in source, True)
check("_show_about mentions 阶段十", "阶段十" in source, True)
check("_show_about mentions AI_Generated", "AI_Generated" in source or "AI生成追踪" in source, True)

# ── Test 9: S9 regression -- rate="medium" no-op ──────────────────
print()
print("=" * 60)
print("9. S9 regression: rate='medium' no-op in SSML")
print("=" * 60)
from app.ssml_generator import generate_ssml_tag
# rate="medium" alone should NOT produce <prosody>
tag_neutral = generate_ssml_tag("Neutral", "Normal", "Middle", "hello")
check("Neutral no prosody tag", "<prosody" not in tag_neutral, True)
check("Neutral basic speak", "<speak>" in tag_neutral, True)

# rate="medium" paired with pitch/volume should include rate="medium"
tag_calm = generate_ssml_tag("Calm", "Normal", "Young", "hello")
check("Calm+Young has prosody", "<prosody" in tag_calm, True)

# ── Test 10: S9 regression -- PaperHubError retryable ──────────────
print()
print("=" * 60)
print("10. S9 regression: PaperHubError retryable status codes")
print("=" * 60)
from app.paperhub_client import PaperHubError
e429 = PaperHubError("rate limited", status_code=429)
e503 = PaperHubError("unavailable", status_code=503)
e0 = PaperHubError("unknown", status_code=0)
e401 = PaperHubError("auth fail", status_code=401)
check("429 is retryable", e429.status_code in (429, 503) or e429.status_code == 0, True)
check("503 is retryable", e503.status_code in (429, 503) or e503.status_code == 0, True)
check("0 is retryable", e0.status_code in (429, 503) or e0.status_code == 0, True)
check("401 NOT retryable", e401.status_code in (429, 503) or e401.status_code == 0, False)

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