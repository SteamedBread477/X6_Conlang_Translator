@echo off
chcp 65001 >nul
echo ============================================================
echo   X6_Conlang_Translator 一键打包脚本
echo ============================================================
echo.

:: 检查 Python 环境
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.9+
    pause
    exit /b 1
)

:: 检查是否在项目目录
if not exist "main.py" (
    echo [错误] 请在项目根目录运行此脚本
    pause
    exit /b 1
)

:: 检查 venv
if not exist "venv\Scripts\python.exe" (
    echo [错误] 未找到 venv，请先创建虚拟环境
    echo   运行: python -m venv venv
    pause
    exit /b 1
)

echo [1/3] 安装依赖...
venv\Scripts\pip.exe install -r requirements.txt -q
if %ERRORLEVEL% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

echo [2/3] 安装 PyInstaller...
venv\Scripts\pip.exe install pyinstaller -q
if %ERRORLEVEL% neq 0 (
    echo [错误] PyInstaller 安装失败
    pause
    exit /b 1
)

echo [3/3] 打包...
venv\Scripts\pyinstaller.exe build.spec --clean --noconfirm
if %ERRORLEVEL% neq 0 (
    echo [错误] 打包失败
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   打包完成！
echo   exe 文件位置: dist\X6_Conlang_Translator.exe
echo ============================================================
echo.
echo 使用方法：
echo   1. 将 dist\X6_Conlang_Translator.exe 复制到目标目录
echo   2. 双击运行即可
echo   3. 首次运行会在 exe 同级目录自动创建 data 文件夹
echo   4. 首次运行会在 exe 同级目录自动创建 app_config.json
echo.

pause