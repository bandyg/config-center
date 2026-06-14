<#
.SYNOPSIS
  Kiosk Config Center — Windows 服务安装/卸载脚本
.DESCRIPTION
  将 KioskConfigCenter.exe 注册为 Windows 服务，实现开机自启。
  使用 NSSM (Non-Sucking Service Manager) 管理服务进程。
.NOTES
  需要以管理员身份运行。
#>

param(
    [ValidateSet("install", "uninstall", "status")]
    [string]$Action = "status"
)

$ServiceName = "KioskConfigCenter"
$ServiceDisplayName = "Kiosk Config Center"
$ExePath = Join-Path $PSScriptRoot "dist\KioskConfigCenter.exe"

# ── 检查 NSSM ──
$NssmPath = "nssm.exe"
$hasNssm = Get-Command $NssmPath -ErrorAction SilentlyContinue

if (-not $hasNssm) {
    Write-Warning "未找到 nssm.exe，请下载 NSSM (https://nssm.cc/download) 并放到 PATH 中"
    Write-Warning "或直接使用: nssm install $ServiceName `"$ExePath`""
    exit 1
}

# ── 检查 EXE ──
if ($Action -ne "status" -and -not (Test-Path $ExePath)) {
    Write-Error "未找到 $ExePath，请先执行 build-windows.bat 构建 EXE"
    exit 1
}

switch ($Action) {
    "install" {
        Write-Host "正在安装 Windows 服务..." -ForegroundColor Cyan
        
        # 检查是否已安装
        $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Host "服务 $ServiceName 已存在，正在删除..." -ForegroundColor Yellow
            & $NssmPath remove $ServiceName confirm
            Start-Sleep -Seconds 2
        }
        
        # 安装服务
        & $NssmPath install $ServiceName $ExePath
        & $NssmPath set $ServiceName DisplayName $ServiceDisplayName
        & $NssmPath set $ServiceName Description "集中管理 Kiosk 终端的配置，提供 Web UI 进行查看、编辑、批量操作和配置对比"
        & $NssmPath set $ServiceName Start SERVICE_AUTO_START
        & $NssmPath set $ServiceName AppStdout (Join-Path $PSScriptRoot "logs\stdout.log")
        & $NssmPath set $ServiceName AppStderr (Join-Path $PSScriptRoot "logs\stderr.log")
        & $NssmPath set $ServiceName AppRotateFiles 1
        & $NssmPath set $ServiceName AppRotateSeconds 86400
        
        Start-Sleep -Seconds 1
        Write-Host "正在启动服务..." -ForegroundColor Cyan
        Start-Service -Name $ServiceName
        
        $svc = Get-Service -Name $ServiceName
        if ($svc.Status -eq "Running") {
            Write-Host "✅ 服务安装成功并已启动" -ForegroundColor Green
            Write-Host "   服务名称: $ServiceName"
            Write-Host "   可执行文件: $ExePath"
            Write-Host "   访问地址: http://localhost:8300"
        } else {
            Write-Host "⚠️ 服务安装完成但状态为 $($svc.Status)" -ForegroundColor Yellow
            Write-Host "   请检查日志: logs\stderr.log"
        }
    }
    
    "uninstall" {
        Write-Host "正在卸载服务..." -ForegroundColor Cyan
        $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if (-not $existing) {
            Write-Host "服务 $ServiceName 未安装" -ForegroundColor Yellow
            return
        }
        
        Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        & $NssmPath remove $ServiceName confirm
        Write-Host "✅ 服务已卸载" -ForegroundColor Green
    }
    
    "status" {
        $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if (-not $svc) {
            Write-Host "❌ 服务 $ServiceName 未安装" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "安装方法: 以管理员身份运行:"
            Write-Host "  .\scripts\install-service.ps1 -Action install"
            return
        }
        
        Write-Host "服务名称: $ServiceName" -ForegroundColor Cyan
        Write-Host "显示名称: $($svc.DisplayName)"
        Write-Host "状态: $($svc.Status)"
        Write-Host "启动类型: $($svc.StartType)"
        Write-Host ""
        
        # 检查端口
        $portCheck = netstat -ano | Select-String ":8300"
        if ($portCheck) {
            Write-Host "端口 8300: ✅ 正在监听" -ForegroundColor Green
        } else {
            Write-Host "端口 8300: ❌ 未监听" -ForegroundColor Red
        }
        
        if ($svc.Status -ne "Running") {
            Write-Host "启动服务: Start-Service -Name $ServiceName"
            Write-Host "停止服务: Stop-Service -Name $ServiceName"
        }
    }
}
