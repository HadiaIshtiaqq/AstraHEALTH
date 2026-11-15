# One-time setup (needs internet once). Afterwards everything runs offline.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "== Backend: virtual environment and dependencies"
Push-Location "$root\backend"
if (-not (Test-Path .venv)) { python -m venv .venv }
& .venv\Scripts\python.exe -m pip install --upgrade pip
& .venv\Scripts\python.exe -m pip install -r requirements.txt
Pop-Location

Write-Host "== Frontend: dependencies and production build"
Push-Location "$root\frontend"
npm install
npm run build
Pop-Location

Write-Host "== Optional: local LLM for plain-language explanations"
if (Get-Command ollama -ErrorAction SilentlyContinue) { ollama pull qwen2.5:3b } else { Write-Host "Ollama not found - the app works without it (deterministic explanations)." }

Write-Host "Setup complete. Start with: scripts\start.ps1"
