param(
    [string]$PythonExe = 'python',
    [int]$Port = 8018
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$runtimeDir = Join-Path $projectRoot '.runtime'
if (-not (Test-Path (Join-Path $projectRoot 'frontend/dist/index.html'))) {
    throw '请先在frontend目录运行 npm ci 和 npm run build。'
}
if (-not (Test-Path (Join-Path $projectRoot 'backend/data/research/manifest.json'))) {
    throw '请先运行 scripts/bootstrap_research.py 导入研究归档。'
}
if (-not (Test-Path $runtimeDir)) { New-Item -ItemType Directory -Path $runtimeDir | Out-Null }
try {
    $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
    if ($health.status -eq 'ok' -and $health.app_id -eq 'nev-mcdm-platform') {
        Write-Output "系统已运行：http://127.0.0.1:$Port"
        exit 0
    }
} catch { }
$pythonCommand = (Get-Command $PythonExe -ErrorAction Stop).Source
$process = Start-Process -FilePath $pythonCommand -ArgumentList '-m', 'uvicorn', 'backend.app:create_app', '--factory', '--host', '127.0.0.1', '--port', "$Port" -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'server.out.log') -RedirectStandardError (Join-Path $runtimeDir 'server.err.log')
$record = @{ process_id = $process.Id; started_at = $process.StartTime.ToUniversalTime().ToString('o'); port = $Port; executable = $pythonCommand }
$record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeDir 'server.json') -Encoding utf8
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 300
    $process.Refresh()
    if ($process.HasExited) { throw "服务启动失败，请查看 $runtimeDir/server.err.log" }
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
        if ($health.status -eq 'ok' -and $health.app_id -eq 'nev-mcdm-platform') {
            Write-Output "系统已启动：http://127.0.0.1:$Port"
            Write-Output "进程ID：$($process.Id)；停止命令：.\scripts\stop-local.ps1"
            exit 0
        }
    } catch { }
}
throw '启动检查超时，请查看.runtime中的日志。'
