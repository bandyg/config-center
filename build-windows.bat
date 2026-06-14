@echo off
REM ============================================
REM Kiosk Config Center - Windows 打包启动器
REM ============================================
REM 双击此 bat 会调用 PowerShell 执行 build-windows.ps1
REM （Trae IDE 的默认终端是 PowerShell 5，bat 在其中执行存在兼容性，
REM  推荐直接用 build-windows.ps1）

where powershell >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 PowerShell
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-windows.ps1"
