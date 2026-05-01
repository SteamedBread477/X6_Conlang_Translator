# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for X6_Conlang_Translator (Nikki Conlang Forge)

打包为单个 exe，data 目录在 exe 旁边运行时自动创建。
"""
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(SPECPATH)

# 分析 app 包下所有 Python 模块
a = Analysis(
    [str(PROJECT_ROOT / 'main.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # 应用图标（运行时也会从 exe 旁 assets/ 目录加载，打包内作为备选）
        ('assets', 'assets'),
    ],
    hiddenimports=[
        # PyQt5 及相关 sip 模块
        'PyQt5',
        'PyQt5.sip',
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        # pandas 及后端
        'pandas',
        'pandas._libs',
        'pandas._libs.tslibs',
        'pandas._libs.tslibs.timedeltas',
        'pandas._libs.tslibs.nattype',
        'pandas._libs.tslibs.offsets',
        'numpy',
        'numpy.core',
        'numpy._core',
        'openpyxl',
        'et_xmlfile',
        # openai
        'openai',
        'httpx',
        'httpcore',
        'anyio',
        'sniffio',
        'h11',
        'certifi',
        'idna',
        'charset_normalizer',
        # 项目模块
        'app',
        'app.app_paths',
        'app.main_window',
        'app.storage',
        'app.parse_lexicon',
        'app.parse_mapping_csv',
        'app.parse_whitepaper',
        'app.parse_history_json',
        'app.rule_translator',
        'app.batch_translator',
        'app.ssml_generator',
        'app.export_result_dialog',
        'app.new_words_report_dialog',
        'app.paperhub_client',
        'app.paperhub_settings',
        'app.paperhub_settings_dialog',
        'app.paperhub_confirm_dialog',
        'app.add_word_dialog',
        'app.unmatched_words_dialog',
        'app.ui_theme',
        'app.lexicon_segment',
        'app.import_classify',
        'app.excel_import',
        'app.history_writer',
        'app.asset_validation',
        'app.material_service',
        'app.batch_translate_dialog',
        'app.appearance_dialog',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大型模块以减小 exe 尺寸
        'tkinter',
        'matplotlib',
        'scipy',
        'PIL',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        'unittest',
        'test',
        'tests',
        'setuptools',
        'pip',
        'wheel',
        'distutils',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='X6_Conlang_Translator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,        # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    targetarch=None,
    codenaming=None,
    icon=str(PROJECT_ROOT / 'assets' / 'app_icon.ico'),  # 从 assets/ 取图标
    version_file=None,
    manifest=None,
    embed_manifest=True,
)