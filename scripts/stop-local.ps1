$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$recordPath = Join-Path $projectRoot '.runtime/server.json'
if (-not (Test-Path $recordPath)) {
    Write-Output '没有本启动脚本的进程记录。'
    return
}

$record = Get-Content -Raw -LiteralPath $recordPath | ConvertFrom-Json
$process = Get-Process -Id $record.process_id -ErrorAction SilentlyContinue
if (-not $process) {
    Remove-Item -LiteralPath $recordPath
    Write-Output '记录的服务已停止，失效记录已清理。'
    return
}

if ($record.started_at -is [DateTime]) {
    $recordedStartTime = $record.started_at.ToUniversalTime()
}
else {
    $recordedStartTime = [DateTimeOffset]::Parse(
        [string]$record.started_at,
        [Globalization.CultureInfo]::InvariantCulture
    ).UtcDateTime
}

$actualStartTime = $process.StartTime.ToUniversalTime()
$recordedExecutable = [IO.Path]::GetFullPath([string]$record.executable)
$actualExecutable = [IO.Path]::GetFullPath([string]$process.Path)
$sameProcess = $actualStartTime.Ticks -eq $recordedStartTime.Ticks -and
    [StringComparer]::OrdinalIgnoreCase.Equals($actualExecutable, $recordedExecutable)

if (-not $sameProcess) {
    throw '进程标识不匹配，不会停止其他进程。'
}

Stop-Process -Id $process.Id -ErrorAction Stop
Remove-Item -LiteralPath $recordPath
Write-Output "本地服务已停止（PID $($process.Id)），数据保留。"
