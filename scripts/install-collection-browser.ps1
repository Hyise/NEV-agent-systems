param(
    [string]$PythonExe = ''
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Resolve-PythonExecutable {
    param([string[]]$Candidates)

    foreach ($candidate in $Candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    throw 'Python 3.11 was not found. Install the backend dependencies first.'
}

$python = Resolve-PythonExecutable -Candidates @(
    $PythonExe,
    (Join-Path $projectRoot '.venv/Scripts/python.exe'),
    'E:\anaconda927\envs\py311\python.exe',
    'python'
)

& $python -m playwright install chromium
if ($LASTEXITCODE -ne 0) {
    throw "Chromium installation failed with exit code $LASTEXITCODE."
}

Write-Output 'The collection browser is ready.'
