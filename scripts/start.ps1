# Start ASTRAHEALTH AI as a single local process (API + built UI) on http://127.0.0.1:8765
param([int]$Port = 8765)
$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\backend"
Write-Host "ASTRAHEALTH AI -> http://127.0.0.1:$Port  (Ctrl+C to stop)"
& .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $Port
