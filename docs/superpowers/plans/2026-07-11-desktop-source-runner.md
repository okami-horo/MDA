# 桌面源码一键运行脚本 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在当前用户桌面创建一个双击后重新构建 Go Agent 并启动 MXU 的单文件脚本。

**Architecture:** 使用一个桌面 `.cmd` 作为入口，通过 PowerShell 7 加载仓库内 `.go\activate.ps1`，调用现有 `tools\build_and_install.py` 完成开发构建，然后启动 `install\mxu.exe`。脚本只编排现有工具，不修改项目业务代码。

**Tech Stack:** Windows CMD、PowerShell 7、Python、项目内 Go 1.25.6、MXU

---

### Task 1: 创建桌面运行脚本

**Files:**
- Create: `C:\Users\Administrator.DESKTOP-1KCKBJ1\OneDrive\Desktop\MDA源码运行.cmd`

- [ ] **Step 1: 确认桌面目录和依赖文件存在**

Run:

```powershell
$desktop = [Environment]::GetFolderPath('Desktop')
[PSCustomObject]@{
    Desktop = $desktop
    Project = Test-Path 'E:\Git\MDA'
    Activate = Test-Path 'E:\Git\MDA\.go\activate.ps1'
    Go = Test-Path 'E:\Git\MDA\.go\sdk\bin\go.exe'
    Builder = Test-Path 'E:\Git\MDA\tools\build_and_install.py'
    MXU = Test-Path 'E:\Git\MDA\install\mxu.exe'
}
```

Expected: 桌面路径为 `C:\Users\Administrator.DESKTOP-1KCKBJ1\OneDrive\Desktop`，其余布尔值均为 `True`。

- [ ] **Step 2: 使用 `apply_patch` 创建单文件脚本**

Create the file with exactly this content:

```batch
@echo off
setlocal
chcp 65001 >nul
title MDA Source Runner

set "PROJECT_ROOT=E:\Git\MDA"

if not exist "%PROJECT_ROOT%" goto :missing_project
if not exist "%PROJECT_ROOT%\.go\activate.ps1" goto :missing_environment
if not exist "%PROJECT_ROOT%\.go\sdk\bin\go.exe" goto :missing_environment
if not exist "%PROJECT_ROOT%\tools\build_and_install.py" goto :missing_builder

where pwsh.exe >nul 2>&1
if errorlevel 1 goto :missing_pwsh

where python.exe >nul 2>&1
if errorlevel 1 goto :missing_python

tasklist /FI "IMAGENAME eq mxu.exe" /NH | "%SystemRoot%\System32\findstr.exe" /I /C:"mxu.exe" >nul
if not errorlevel 1 goto :mxu_running

pwsh.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; Set-Location -LiteralPath '%PROJECT_ROOT%'; . '.\.go\activate.ps1'; python 'tools\build_and_install.py'; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; if (-not (Test-Path '.\install\mxu.exe')) { Write-Error 'install\mxu.exe is missing. Run tools\setup_workspace.py first.'; exit 2 }; Start-Process -FilePath (Resolve-Path '.\install\mxu.exe') -WorkingDirectory (Resolve-Path '.\install')"
if errorlevel 1 goto :build_failed

exit /b 0

:missing_project
echo Project directory not found: %PROJECT_ROOT%
goto :failed

:missing_environment
echo Local Go environment is missing. Run the project setup first.
goto :failed

:missing_builder
echo Build script not found: %PROJECT_ROOT%\tools\build_and_install.py
goto :failed

:missing_pwsh
echo PowerShell 7 ^(pwsh.exe^) was not found.
goto :failed

:missing_python
echo Python ^(python.exe^) was not found.
goto :failed

:mxu_running
echo MXU is already running. Close MXU and run this script again.
goto :failed

:build_failed
echo MDA build or launch failed.

:failed
pause
exit /b 1
```

- [ ] **Step 3: 检查脚本文本内容**

Run:

```powershell
Get-Content -Raw 'C:\Users\Administrator.DESKTOP-1KCKBJ1\OneDrive\Desktop\MDA源码运行.cmd'
```

Expected: 输出包含 `build_and_install.py`、`.go\activate.ps1`、`tasklist` 和 `install\mxu.exe`。

### Task 2: 验证错误分支和成功启动

**Files:**
- Test: `C:\Users\Administrator.DESKTOP-1KCKBJ1\OneDrive\Desktop\MDA源码运行.cmd`

- [ ] **Step 1: 检查现有 MXU 进程**

Run:

```powershell
Get-Process -Name mxu -ErrorAction SilentlyContinue
```

Expected: 若存在进程，脚本应显示 `MXU is already running` 并返回退出码 `1`；关闭 MXU 后继续成功路径验证。

- [ ] **Step 2: 执行桌面脚本**

Run:

```powershell
& 'C:\Users\Administrator.DESKTOP-1KCKBJ1\OneDrive\Desktop\MDA源码运行.cmd'
```

Expected: `build_and_install.py` 返回成功，随后启动 `E:\Git\MDA\install\mxu.exe`。

- [ ] **Step 3: 验证构建产物和 MXU 进程**

Run:

```powershell
[PSCustomObject]@{
    GoAgent = Test-Path 'E:\Git\MDA\install\agent\go-service.exe'
    MXU = Test-Path 'E:\Git\MDA\install\mxu.exe'
    MxuRunning = [bool](Get-Process -Name mxu -ErrorAction SilentlyContinue)
}
```

Expected: 三项均为 `True`。

- [ ] **Step 4: 确认项目工作树没有被桌面脚本修改**

Run:

```powershell
git -C E:\Git\MDA status --short
```

Expected: 不出现桌面脚本或其他意外变化；只允许已提交的设计与计划历史存在。
