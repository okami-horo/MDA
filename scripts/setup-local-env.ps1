#Requires -Version 7
<#
.SYNOPSIS
    初始化 MDA 项目局部开发环境（不污染系统/C盘）。
.DESCRIPTION
    在项目目录内创建隔离环境：
    - Node: npm install -> ./node_modules（npm 默认局部）
    - Python: python -m venv -> ./.venv
    - Go: GOPATH -> ./.go，go mod download 局部缓存
    运行后使用 ./scripts/Activate-LocalEnv.ps1 激活环境变量。
#>
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot | Resolve-Path

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "MDA 项目局部开发环境初始化" -ForegroundColor Cyan
Write-Host "项目根目录: $ProjectRoot" -ForegroundColor Gray
Write-Host "========================================" -ForegroundColor Cyan

# ---------- Node.js ----------
Write-Host "`n[1/3] Node.js (npm install)" -ForegroundColor Yellow
$nodeVersion = & node --version 2>$null
if ($LASTEXITCODE -ne 0 -or -not $nodeVersion) {
    Write-Host "  错误: 未检测到 Node.js，请先安装 Node.js (https://nodejs.org)" -ForegroundColor Red
    exit 1
}
Write-Host "  Node 版本: $nodeVersion" -ForegroundColor Gray
Set-Location $ProjectRoot
& npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "  npm install 失败" -ForegroundColor Red
    exit 1
}
Write-Host "  node_modules 已创建（项目局部）" -ForegroundColor Green

# ---------- Python ----------
Write-Host "`n[2/3] Python 虚拟环境 (.venv)" -ForegroundColor Yellow
$pyCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pyCmd) { $pyCmd = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $pyCmd) {
    Write-Host "  错误: 未检测到 Python，请先安装 Python 3 (https://python.org)" -ForegroundColor Red
    exit 1
}
$pyVersion = & $pyCmd.Source --version 2>&1
Write-Host "  Python: $pyVersion" -ForegroundColor Gray

$venvPath = Join-Path $ProjectRoot ".venv"
if (Test-Path $venvPath) {
    Write-Host "  .venv 已存在，跳过创建" -ForegroundColor DarkYellow
} else {
    & $pyCmd.Source -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  创建 .venv 失败" -ForegroundColor Red
        exit 1
    }
    Write-Host "  .venv 已创建" -ForegroundColor Green
}

$pipExe = Join-Path $venvPath "Scripts\pip.exe"
& $pipExe install --upgrade pip | Out-Null
$reqFile = Join-Path $ProjectRoot "tools\requirements.txt"
if (Test-Path $reqFile) {
    & $pipExe install -r $reqFile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  pip install 失败" -ForegroundColor Red
        exit 1
    }
    Write-Host "  tools/requirements.txt 已安装到 .venv" -ForegroundColor Green
}
$reqFile2 = Join-Path $ProjectRoot "tools\optimize_templates\requirements.txt"
if (Test-Path $reqFile2) {
    & $pipExe install -r $reqFile2
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  optimize_templates/requirements.txt 安装失败" -ForegroundColor Red
    } else {
        Write-Host "  optimize_templates/requirements.txt 已安装到 .venv" -ForegroundColor Green
    }
}

# ---------- Go ----------
Write-Host "`n[3/3] Go 局部 GOPATH (.go)" -ForegroundColor Yellow
$goVersion = & go version 2>$null
if ($LASTEXITCODE -ne 0 -or -not $goVersion) {
    Write-Host "  错误: 未检测到 Go，请先安装 Go 1.25+ (https://go.dev/dl)" -ForegroundColor Red
    exit 1
}
Write-Host "  $goVersion" -ForegroundColor Gray

$goPath = Join-Path $ProjectRoot ".go"
$env:GOPATH = $goPath
$env:GOMODCACHE = Join-Path $goPath "pkg\mod"

Write-Host "  GOPATH  -> $goPath" -ForegroundColor Gray
Write-Host "  GOMODCACHE -> $env:GOMODCACHE" -ForegroundColor Gray

$goServiceDir = Join-Path $ProjectRoot "agent\go-service"
Set-Location $goServiceDir
& go mod download
if ($LASTEXITCODE -ne 0) {
    Write-Host "  go mod download 失败" -ForegroundColor Red
    exit 1
}
Write-Host "  Go 依赖已下载到 .go/pkg/mod（项目局部）" -ForegroundColor Green

# ---------- 生成激活脚本 ----------
Write-Host "`n[生成激活脚本]" -ForegroundColor Yellow
$activateScript = Join-Path $ProjectRoot "scripts\Activate-LocalEnv.ps1"
$activateContent = @"
#Requires -Version 7
<#
.SYNOPSIS
    激活 MDA 项目局部开发环境变量。
.DESCRIPTION
    在当前 PowerShell 会话中设置：
    - Python: 激活 .venv
    - Go:     设置 GOPATH 为项目 .go 目录
    - Node:   使用项目 node_modules/.bin
    用法: . ./scripts/Activate-LocalEnv.ps1   (注意前面的点)
#>
`$ProjectRoot = Split-Path -Parent `$PSScriptRoot | Resolve-Path

# Python
`$venvActivate = Join-Path `$ProjectRoot ".venv\Scripts\Activate.ps1"
if (Test-Path `$venvActivate) {
    . `$venvActivate
} else {
    Write-Warning ".venv 激活脚本不存在，请先运行 setup-local-env.ps1"
}

# Go
`$env:GOPATH = Join-Path `$ProjectRoot ".go"
`$env:GOMODCACHE = Join-Path `$env:GOPATH "pkg\mod"

# Node local bin
`$nodeBin = Join-Path `$ProjectRoot "node_modules\.bin"
if (`$env:Path -notlike "*`$nodeBin*") {
    `$env:Path = "`$nodeBin;`$env:Path"
}

Write-Host "MDA 局部环境已激活" -ForegroundColor Green
Write-Host "  GOPATH:     `$env:GOPATH" -ForegroundColor Gray
Write-Host "  GOMODCACHE: `$env:GOMODCACHE" -ForegroundColor Gray
Write-Host "  PYTHON:     `$(Get-Command python | Select-Object -ExpandProperty Source)" -ForegroundColor Gray
"@
Set-Content -Path $activateScript -Value $activateContent -Encoding UTF8
Write-Host "  已生成: scripts\Activate-LocalEnv.ps1" -ForegroundColor Green

# ---------- 完成 ----------
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "局部环境初始化完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "`n后续步骤:" -ForegroundColor White
Write-Host "  1. 激活环境变量:" -ForegroundColor Gray
Write-Host "     . ./scripts/Activate-LocalEnv.ps1" -ForegroundColor Cyan
Write-Host "  2. 运行 Go Agent:" -ForegroundColor Gray
Write-Host "     cd agent/go-service; go build" -ForegroundColor Cyan
Write-Host "  3. 运行工具脚本:" -ForegroundColor Gray
Write-Host "     python tools/xxx.py" -ForegroundColor Cyan
Write-Host "`n所有依赖均位于项目目录内，不影响系统环境。" -ForegroundColor Gray
