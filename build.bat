@echo off
chcp 65001 >nul
echo ============================================================
echo   Nikki Conlang Forge 一键打包 + 安装器脚本
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

echo [2/3] 打包发布目录（PyInstaller + 文件收集）...
venv\Scripts\python.exe pack_release.py
if %ERRORLEVEL% neq 0 (
    echo [错误] 打包失败
    pause
    exit /b 1
)

echo [3/3] 生成 NSIS 安装器...

:: installer.nsi 的 UTF-8 BOM 编码已由 pack_release.py 的 ensure_nsi_bom() 自动处理
:: 无需在此处手动转换

set NSIS_PATH=C:\Program Files (x86)\NSIS\makensis.exe
if not exist "%NSIS_PATH%" (
    echo [警告] 未找到 NSIS (makensis.exe)，跳过安装器生成
    echo   安装器需手动安装 NSIS 3.x: https://nsis.sourceforge.io/
    echo   或运行: winget install NSIS.NSIS
    echo.
    echo   发布目录已就绪: dist\Nikki Conlang Forge\
    echo   手动编译安装器: makensis installer.nsi
    pause
    exit /b 0
)

"%NSIS_PATH%" installer.nsi
if %ERRORLEVEL% neq 0 (
    echo [错误] 安装器编译失败
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   打包完成！
echo ============================================================
echo.
echo   发布目录: dist\Nikki Conlang Forge\
echo   安装器:   dist\Nikki_Conlang_Forge_Setup.exe
echo.
echo   使用方法：
echo   1. 双击 Nikki_Conlang_Forge_Setup.exe 安装
echo   2. 安装完成后桌面/开始菜单有快捷方式
echo   3. 首次运行时 PaperHub 默认关闭，需手动配置 API Key
echo.

pause