$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
$requirementsHash = (Get-FileHash -LiteralPath 'requirements.txt' -Algorithm SHA256).Hash
$stampPath = Join-Path $PSScriptRoot '.venv/requirements.sha256'
$previousHash = if (Test-Path -LiteralPath $stampPath) { (Get-Content -LiteralPath $stampPath -Raw).Trim() } else { '' }
if ($requirementsHash -ne $previousHash) {
    & $pythonPath -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Could not install project dependencies.' }
    Set-Content -LiteralPath $stampPath -Value $requirementsHash
}
$env:ALLOW_DEV_AUTH = 'true'
$env:HOST = '127.0.0.1'
$env:BOT_TOKEN = ''
$env:PYTHONIOENCODING = 'utf-8'
Write-Host 'LingoPal: http://127.0.0.1:3000 (Ctrl+C to stop)'
& $pythonPath run.py
