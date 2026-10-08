import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell compatibility test")
def test_windows_powershell_can_parse_all_launcher_scripts() -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell is not None

    parser_command = (
        "$tokens = $null; $errors = $null; "
        "[System.Management.Automation.Language.Parser]::ParseFile("
        "$env:SCRIPT_UNDER_TEST, [ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { "
        "$errors | ForEach-Object { Write-Error $_.Message }; exit 1 }"
    )

    for script_name in ("start-site.ps1", "start-local.ps1", "stop-local.ps1"):
        env = os.environ.copy()
        env["SCRIPT_UNDER_TEST"] = str(SCRIPTS_DIR / script_name)
        result = subprocess.run(
            [powershell, "-NoProfile", "-Command", parser_command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=False,
        )
        assert result.returncode == 0, f"{script_name}: {result.stderr or result.stdout}"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher integration test")
def test_start_site_repairs_stale_node_modules_before_building(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell is not None

    project_root = tmp_path / "project"
    scripts_dir = project_root / "scripts"
    frontend_dir = project_root / "frontend"
    source_dir = frontend_dir / "src"
    node_modules_dir = frontend_dir / "node_modules"
    scripts_dir.mkdir(parents=True)
    source_dir.mkdir(parents=True)
    node_modules_dir.mkdir()

    start_site = scripts_dir / "start-site.ps1"
    shutil.copy2(SCRIPTS_DIR / "start-site.ps1", start_site)
    (scripts_dir / "start-local.ps1").write_text(
        "param([string]$PythonExe, [int]$Port)\n",
        encoding="utf-8-sig",
    )
    (source_dir / "main.ts").write_text("export {};\n", encoding="utf-8")
    (frontend_dir / "package.json").write_text("{}\n", encoding="utf-8")
    (frontend_dir / "package-lock.json").write_text("{}\n", encoding="utf-8")
    (frontend_dir / "vite.config.ts").write_text("export default {};\n", encoding="utf-8")
    (frontend_dir / "index.html").write_text("<!doctype html>\n", encoding="utf-8")

    npm_log = tmp_path / "npm.log"
    fake_npm = tmp_path / "npm.cmd"
    fake_npm.write_text(
        """@echo off
if /I not "%CD%"=="%EXPECTED_NPM_CWD%" (
  echo wrong-directory %*>>"%NPM_LOG%"
  exit /b 0
)
echo %*>>"%NPM_LOG%"
if "%1"=="ls" exit /b 1
if "%1"=="install" exit /b 0
if "%1"=="run" (
  if "%2"=="build" (
    if not exist "%FAKE_DIST_DIR%" mkdir "%FAKE_DIST_DIR%"
    >"%FAKE_DIST_DIR%\\index.html" echo ^<!doctype html^>
  )
)
exit /b 0
""",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update(
        {
            "EXPECTED_NPM_CWD": str(frontend_dir),
            "FAKE_DIST_DIR": str(frontend_dir / "dist"),
            "NPM_LOG": str(npm_log),
        }
    )
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(start_site),
            "-PythonExe",
            sys.executable,
            "-NpmExe",
            str(fake_npm),
            "-NoBrowser",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert npm_log.read_text(encoding="utf-8").splitlines() == [
        "ls --depth=0 --silent",
        "install",
        "run build",
    ]


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell process integration test")
def test_stop_script_accepts_json_datetime_and_removes_process_record(tmp_path: Path) -> None:
    pwsh = shutil.which("pwsh.exe")
    if pwsh is None:
        pytest.skip("PowerShell 7 is not installed")

    scripts_dir = tmp_path / "scripts"
    runtime_dir = tmp_path / ".runtime"
    scripts_dir.mkdir()
    runtime_dir.mkdir()
    stop_script = scripts_dir / "stop-local.ps1"
    shutil.copy2(SCRIPTS_DIR / "stop-local.ps1", stop_script)
    record_path = runtime_dir / "server.json"

    harness = r"""
$ErrorActionPreference = 'Stop'
$child = Start-Process -FilePath $env:DUMMY_PYTHON -ArgumentList '-c', 'import time; time.sleep(60)' -PassThru
try {
    $record = @{
        process_id = $child.Id
        started_at = $child.StartTime.ToUniversalTime().ToString('o')
        port = 0
        executable = $child.Path
    }
    $record | ConvertTo-Json | Set-Content -LiteralPath $env:RECORD_PATH -Encoding utf8
    & $env:STOP_SCRIPT
    $child.Refresh()
    if (-not $child.HasExited) { throw '停止脚本没有结束目标进程。' }
    if (Test-Path -LiteralPath $env:RECORD_PATH) { throw '停止后仍残留进程记录。' }
}
finally {
    $child.Refresh()
    if (-not $child.HasExited) { Stop-Process -Id $child.Id -Force }
}
"""
    env = os.environ.copy()
    env.update(
        {
            "DUMMY_PYTHON": sys.executable,
            "RECORD_PATH": str(record_path),
            "STOP_SCRIPT": str(stop_script),
        }
    )

    result = subprocess.run(
        [pwsh, "-NoProfile", "-Command", harness],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
