param(
    [string]$PythonExe = '',
    [string]$NpmExe = '',
    [int]$Port = 8029,
    [switch]$NoBrowser,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$frontendRoot = Join-Path $projectRoot 'frontend'
$distIndex = Join-Path $frontendRoot 'dist/index.html'

function Resolve-Executable {
    param(
        [string[]]$Candidates,
        [string]$DisplayName
    )

    foreach ($candidate in $Candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }

    throw "未找到$DisplayName。请先按 docs/运行须知.md 完成环境准备。"
}

$python = Resolve-Executable -DisplayName 'Python 3.11 运行环境' -Candidates @(
    $PythonExe,
    (Join-Path $projectRoot '.venv/Scripts/python.exe'),
    'E:\anaconda927\envs\py311\python.exe',
    'python'
)

$frontendInputs = @(
    Get-ChildItem -LiteralPath (Join-Path $frontendRoot 'src') -Recurse -File
    Get-Item -LiteralPath (Join-Path $frontendRoot 'package.json')
    Get-Item -LiteralPath (Join-Path $frontendRoot 'package-lock.json')
    Get-Item -LiteralPath (Join-Path $frontendRoot 'vite.config.ts')
    Get-Item -LiteralPath (Join-Path $frontendRoot 'index.html')
)
$latestFrontendChange = $frontendInputs |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
$needsBuild = -not (Test-Path -LiteralPath $distIndex)
if (-not $needsBuild) {
    $needsBuild = $latestFrontendChange.LastWriteTimeUtc -gt (Get-Item -LiteralPath $distIndex).LastWriteTimeUtc
}

if ($needsBuild -and -not $SkipBuild) {
    $npm = Resolve-Executable -DisplayName 'npm.cmd' -Candidates @(
        $NpmExe,
        'E:\aaaxz\nodejs0324\npm.cmd',
        'npm.cmd'
    )

    Push-Location $frontendRoot
    try {
        $dependenciesReady = $false
        if (Test-Path -LiteralPath (Join-Path $frontendRoot 'node_modules')) {
            & $npm ls --depth=0 --silent | Out-Null
            $dependenciesReady = $LASTEXITCODE -eq 0
        }

        if (-not $dependenciesReady) {
            Write-Output '检测到前端依赖缺失或版本不一致，正在安装依赖…'
            & $npm install
            if ($LASTEXITCODE -ne 0) { throw "前端依赖安装失败（退出码 $LASTEXITCODE）。" }
        }

        Write-Output '检测到前端源码有更新，正在生成生产页面…'
        & $npm run build
        if ($LASTEXITCODE -ne 0) { throw "前端构建失败（退出码 $LASTEXITCODE）。" }
    }
    finally {
        Pop-Location
    }
}

& (Join-Path $PSScriptRoot 'start-local.ps1') -PythonExe $python -Port $Port

$siteUrl = "http://127.0.0.1:$Port/"
if (-not $NoBrowser) {
    Start-Process $siteUrl
    Write-Output "已在默认浏览器打开：$siteUrl"
}
