# Kiosk Config Center - Windows packaging script (PowerShell 5 compatible)
# Usage: powershell -ExecutionPolicy Bypass -File build-windows.ps1

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Continue"

Write-Host "========================================"
Write-Host " Kiosk Config Center - Windows Packaging"
Write-Host "========================================"

# 1) Check Python
Write-Host "[1/5] Checking Python..."
$pythonCheck = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Please install Python 3.11+ first" -ForegroundColor Red
    pause
    exit 1
}
Write-Host "       OK ($pythonCheck)" -ForegroundColor Green

# 2) Create venv
Write-Host "[2/5] Creating virtual environment..."
$venvPy = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    python -m venv (Join-Path $PSScriptRoot "venv") 2>&1 | Out-Null
}
if (-not (Test-Path $venvPy)) {
    Write-Host "[ERROR] Failed to create venv" -ForegroundColor Red
    pause
    exit 1
}
Write-Host "       OK" -ForegroundColor Green

# 3) Install dependencies (multi-mirror fallback)
Write-Host "[3/5] Installing dependencies (multi-mirror fallback)..."
$mirrors = @(
    "https://pypi.tuna.tsinghua.edu.cn/simple",
    "https://mirrors.aliyun.com/pypi/simple",
    "https://mirrors.cloud.tencent.com/pypi/simple",
    "https://pypi.org/simple"
)

& $venvPy -m pip install --upgrade pip -i $mirrors[0] --timeout 60 2>&1 | Out-Null

$depsOK = $false
foreach ($m in $mirrors) {
    Write-Host "       Trying mirror: $m"
    & $venvPy -m pip install -r (Join-Path $PSScriptRoot "requirements.txt") -i $m --timeout 120 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $depsOK = $true; break }
}
if (-not $depsOK) {
    Write-Host "[ERROR] All mirrors failed" -ForegroundColor Red
    pause
    exit 1
}

$pyiOK = $false
foreach ($m in $mirrors) {
    Write-Host "       Trying mirror: $m"
    & $venvPy -m pip install pyinstaller -i $m --timeout 120 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { $pyiOK = $true; break }
}
if (-not $pyiOK) {
    Write-Host "[ERROR] pyinstaller installation failed" -ForegroundColor Red
    pause
    exit 1
}
Write-Host "       OK" -ForegroundColor Green

# 4) Clean old artifacts
Write-Host "[4/5] Cleaning old artifacts..."
foreach ($d in @("build", "dist")) {
    $full = Join-Path $PSScriptRoot $d
    if (Test-Path $full) { Remove-Item -Recurse -Force $full }
}
$spec = Join-Path $PSScriptRoot "KioskConfigCenter.spec"
if (Test-Path $spec) { Remove-Item -Force $spec }
Write-Host "       OK" -ForegroundColor Green

# 5) Build EXE
Write-Host "[5/5] Building EXE, please wait 1-3 minutes..."
$pyiExe = Join-Path $PSScriptRoot "venv\Scripts\pyinstaller.exe"
$argList = @(
    "--noconfirm", "--clean",
    "--onefile",
    "--name", "KioskConfigCenter",
    "--add-data", "app/templates;app/templates",
    "--add-data", "app/static;app/static",
    "--add-data", "terminals.yaml;.",
    "--add-data", "servers.yaml;.",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols",
    "--hidden-import", "uvicorn.protocols.http",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.websockets",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "uvicorn.lifespan",
    "--hidden-import", "uvicorn.lifespan.on",
    "--collect-all", "fastapi",
    "--collect-all", "uvicorn",
    "run.py"
)
$argList = @(
    "--noconfirm", "--clean",
    "--console",
    "--onefile",
    "--name", "KioskConfigCenter",
    "--add-data", "app/templates;app/templates",
    "--add-data", "app/static;app/static",
    "--add-data", "terminals.yaml;.",
    "--add-data", "servers.yaml;.",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols",
    "--hidden-import", "uvicorn.protocols.http",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.websockets",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "uvicorn.lifespan",
    "--hidden-import", "uvicorn.lifespan.on",
    "--collect-all", "fastapi",
    "--collect-all", "uvicorn",
    "--collect-submodules", "app",
    "--collect-data", "app",
    "run.py"
)
& $pyiExe $argList
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Build failed" -ForegroundColor Red
    pause
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host " [OK] Build complete" -ForegroundColor Green
Write-Host " Output: dist\KioskConfigCenter.exe"
Write-Host " Double-click to launch the config center"
Write-Host "========================================" -ForegroundColor Green
pause
