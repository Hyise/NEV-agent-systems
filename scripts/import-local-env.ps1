function Import-LocalEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
    foreach ($rawLine in [System.IO.File]::ReadAllLines($Path)) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#')) { continue }
        if ($line -notmatch '^[A-Za-z_][A-Za-z0-9_]*=') { continue }

        $separator = $line.IndexOf('=')
        $name = $line.Substring(0, $separator)
        $value = $line.Substring($separator + 1)
        if ($null -eq [Environment]::GetEnvironmentVariable($name, 'Process')) {
            Set-Item -LiteralPath "Env:$name" -Value $value
        }
    }
}

