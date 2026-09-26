$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$recordPath = Join-Path $projectRoot '.runtime/server.json'
if (-not (Test-Path $recordPath)) { Write-Output '没有本启动脚本的进程记录。'; exit 0 }
$record = Get-Content -Raw -LiteralPath $recordPath | ConvertFrom-Json
$process = Get-Process -Id $record.process_id -ErrorAction SilentlyContinue
if (-not $process) { Write-Output '记录的服务已停止。'; exit 0 }
if ($process.StartTime.ToUniversalTime().ToString('o') -ne $record.started_at -or $process.Path -ne $record.executable) {
    throw '进程标识不匹配，不会停止其他进程。'
}
Stop-Process -Id $process.Id
Write-Output "本地服务已停止（PID $($process.Id)），数据保留。"
