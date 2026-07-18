# Modpack Manager launcher (PowerShell).
# Run from this folder:  .\run.ps1
# If PowerShell blocks it: powershell -ExecutionPolicy Bypass -File .\run.ps1
Set-Location -Path $PSScriptRoot

$py = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "First run: creating the virtual environment and installing dependencies..."
    Write-Host "(needs Python 3.10+ on your PATH)"
    python -m venv .venv
    & $py -m pip install --upgrade pip -q
    & $py -m pip install -r requirements.txt -q
    & $py -m pip install -e . -q
}

Write-Host ""
Write-Host "Starting Modpack Manager -- your browser will open at http://127.0.0.1:5178"
Write-Host "Press Ctrl+C to stop."
Write-Host ""
& $py -m modpack_manager
