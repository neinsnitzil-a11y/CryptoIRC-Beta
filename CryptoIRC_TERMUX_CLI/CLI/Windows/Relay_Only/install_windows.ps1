# VaultForge Unified bootstrap. No administrator rights or system Python changes.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$runtime = Join-Path $PSScriptRoot '.runtime'
$uvDir = Join-Path $runtime 'uv'
$uvPath = Join-Path $uvDir 'uv.exe'
$env:UV_NO_CONFIG = '1'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $runtime 'python'
$env:UV_PYTHON_BIN_DIR = Join-Path $runtime 'bin'
# Use an already installed CPython 3.12 without network access when possible.
$python312 = $null
$launcher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($launcher) {
    try {
        $candidate = (& $launcher.Source -3.12 -c 'import sys; assert sys.version_info[:2] == (3,12); print(sys.executable)' 2>$null | Select-Object -Last 1)
        if ($LASTEXITCODE -eq 0 -and $candidate -and (Test-Path -LiteralPath $candidate.Trim() -PathType Leaf)) {
            $python312 = $candidate.Trim()
            Write-Host "[SETUP] Using existing Python 3.12: $python312"
        }
    } catch { }
}


try {
    if (-not $python312) {
        if (-not (Test-Path -LiteralPath $uvPath -PathType Leaf)) {
            $found = Get-Command uv -ErrorAction SilentlyContinue
            if ($found) { $uvPath = $found.Source }
        }
        if (-not (Test-Path -LiteralPath $uvPath -PathType Leaf)) {
            Write-Host '[SETUP] Downloading the official uv bootstrap (time-limited; no admin)...'
            New-Item -ItemType Directory -Path $uvDir -Force | Out-Null
            $installer = Join-Path ([System.IO.Path]::GetTempPath()) ('vaultforge-uv-' + [guid]::NewGuid().ToString('N') + '.ps1')
            try {
                Invoke-WebRequest -UseBasicParsing -TimeoutSec 60 -Uri 'https://astral.sh/uv/install.ps1' -OutFile $installer
                $env:UV_UNMANAGED_INSTALL = $uvDir
                $proc = Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $installer + '"')) -NoNewWindow -PassThru
                if (-not $proc.WaitForExit(180000)) {
                    $proc.Kill()
                    throw 'uv binary download exceeded 180 seconds. Check HTTPS access and retry.'
                }
                if ($proc.ExitCode -ne 0) { throw "Official uv bootstrap exited with code $($proc.ExitCode)." }
            } finally {
                Remove-Item -LiteralPath $installer -Force -ErrorAction SilentlyContinue
                Remove-Item Env:UV_UNMANAGED_INSTALL -ErrorAction SilentlyContinue
            }
            $uvPath = Join-Path $uvDir 'uv.exe'
        }
        if (-not (Test-Path -LiteralPath $uvPath -PathType Leaf)) { throw 'uv.exe not found after installation.' }

        Write-Host '[SETUP] Installing/reusing CPython 3.12 (isolated from system Python)...'
        & $uvPath python install 3.12
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 download or installation failed.' }
        $python312 = (& $uvPath python find 3.12 --managed-python | Select-Object -Last 1)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($python312)) {
            throw 'Could not locate managed Python 3.12.'
        }
        $python312 = $python312.Trim()
        if (-not (Test-Path -LiteralPath $python312 -PathType Leaf)) {
            throw "Python 3.12 executable not found: $python312"
        }
        $env:VAULTFORGE_UV = $uvPath
    }
    $env:VAULTFORGE_PYTHON = $python312
    & $python312 (Join-Path $PSScriptRoot 'install_runtime.py')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation or self-tests failed.' }
    Write-Host '[OK] VaultForge installed with Python 3.12.'
    exit 0
} catch {
    Write-Error ("[ERROR] " + $_.Exception.Message)
    exit 1
}
