; ── Nikki Conlang Forge NSIS 安装脚本 ──────────────────────────────
;
; 使用方式：
;   makensis installer.nsi
;
; 前置条件：
;   1. 先运行 pack_release.py 生成 dist/Nikki Conlang Forge/ 发布目录
;   2. NSIS 3.x 已安装（makensis 可用）
;
; 安装行为：
;   - 安装到 $LOCALAPPDATA\Nikki Conlang Forge（用户可写目录，无需管理员权限）
;   - 创建桌面快捷方式 + 开始菜单快捷方式
;   - 卸载时保留用户数据（data/ 和 app_config.json）

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"

; ── 编译设置 ──────────────────────────────────────────────────────
Unicode true
SetCompressor /SOLID lzma
SetCompressorDictSize 32

; ── 应用信息 ──────────────────────────────────────────────────────
!define APP_NAME "Nikki Conlang Forge"
!define APP_EXE "Nikki Conlang Forge.exe"
!define APP_VERSION "1.0.0"
!define APPPublisher "蒸汽面包"
!define APP_ICON "assets\app_icon.ico"

; ── 安装路径 ──────────────────────────────────────────────────────
Name "${APP_NAME}"
OutFile "dist\Nikki_Conlang_Forge_Setup.exe"
InstallDir "$LOCALAPPDATA\${APP_NAME}"
InstallDirRegKey HKCU "Software\${APP_NAME}" "InstallDir"
RequestExecutionLevel user

; ── 界面设置 ──────────────────────────────────────────────────────
!define MUI_ICON "${APP_ICON}"
!define MUI_UNICON "${APP_ICON}"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "立即运行 ${APP_NAME}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

; ── 版本信息（EXE 文件属性）─────────────────────────────────────
VIProductVersion "${APP_VERSION}.0"
VIAddVersionKey /LANG=${LANG_SIMPCHINESE} "ProductName" "${APP_NAME}"
VIAddVersionKey /LANG=${LANG_SIMPCHINESE} "CompanyName" "${APPPublisher}"
VIAddVersionKey /LANG=${LANG_SIMPCHINESE} "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=${LANG_SIMPCHINESE} "FileDescription" "人造语言翻译器"
VIAddVersionKey /LANG=${LANG_SIMPCHINESE} "LegalCopyright" "Copyright © 2026 蒸汽面包"

; ── 安装段 ──────────────────────────────────────────────────────

Section "!主程序" SecMain
    SectionIn RO

    SetOutPath "$INSTDIR"

    ; 写入安装路径到注册表
    WriteRegStr HKCU "Software\${APP_NAME}" "InstallDir" "$INSTDIR"

    ; ── 复制发布目录内容 ────────────────────────────────────────

    ; 主程序 EXE
    File "dist\Nikki Conlang Forge\${APP_EXE}"

    ; 运行时依赖 _internal/
    SetOutPath "$INSTDIR\_internal"
    File /r "dist\Nikki Conlang Forge\_internal\*.*"

    ; 资源目录 assets/
    SetOutPath "$INSTDIR\assets"
    File /r "dist\Nikki Conlang Forge\assets\*.*"

    ; 语言数据（config.json + 3种语言子目录）
    SetOutPath "$INSTDIR\data"
    File /r /x "languages" /x "derived" "dist\Nikki Conlang Forge\data\*.*"

    SetOutPath "$INSTDIR"

    ; 用户预设配置（含词作模版 ask_templates、字体偏好 font_settings 等；
    ; 敏感字段 paperhub_api_key / paperhub_enabled 已在打包时清除）
    File "dist\Nikki Conlang Forge\app_config.json"

    ; ── 写入卸载信息到注册表 ────────────────────────────────────
    WriteUninstaller "$INSTDIR\uninstall.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "Publisher" "${APPPublisher}"
    WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "InstallLocation" "$INSTDIR"

    ; 计算安装大小
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "EstimatedSize" "$0"

SectionEnd

; ── 快捷方式段 ──────────────────────────────────────────────────

Section "桌面快捷方式" SecDesktop
    CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
SectionEnd

Section "开始菜单快捷方式" SecStartMenu
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\${APP_EXE}" 0
    CreateShortCut "$SMPROGRAMS\${APP_NAME}\卸载.lnk" "$INSTDIR\uninstall.exe"
SectionEnd

; ── 快捷方式段结束 ───────────────────────────────────────────────

; ── 卸载段 ──────────────────────────────────────────────────────

Section "Uninstall"
    ; 删除快捷方式
    Delete "$DESKTOP\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\卸载.lnk"
    RMDir "$SMPROGRAMS\${APP_NAME}"

    ; 删除程序文件（但保留用户数据）
    Delete "$INSTDIR\${APP_EXE}"
    Delete "$INSTDIR\uninstall.exe"
    RMDir /r "$INSTDIR\_internal"

    ; 保留 assets/（用户可能自定义了图标）
    ; 保留 data/（含语言包和翻译历史）
    ; 保留 app_config.json（含 API Key 和字体偏好）
    ; 如需彻底清理，取消注释以下三行：
    ; RMDir /r "$INSTDIR\assets"
    ; RMDir /r "$INSTDIR\data"
    ; Delete "$INSTDIR\app_config.json"

    ; 尝试删除安装目录（如果 data/assets 没有占住则成功）
    RMDir "$INSTDIR"

    ; 删除注册表
    DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
    DeleteRegKey HKCU "Software\${APP_NAME}"
SectionEnd