# VaultForge Unified CLI (PowerShell entry point; no BAT wrappers)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'VaultForge CLI runtime missing. Run: powershell -NoProfile -ExecutionPolicy Bypass -File .\install_windows.ps1'
}
& $python -I (Join-Path $PSScriptRoot 'vaultforge.py') @args
exit $LASTEXITCODE
