# All automated tests: backend (pytest), frontend unit (Vitest), browser flows + WCAG audit in Edge and Chrome (Playwright).
$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\backend"
& .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
Set-Location "$root\frontend"
npx vitest run src
npx playwright test
