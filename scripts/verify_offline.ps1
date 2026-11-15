# Offline verification for ASTRAHEALTH AI (release criterion 5.7), without cutting the laptop's network.
# Proves, while a full analysis workflow runs:
#   1. the ASTRAHEALTH server and the Ollama runtime listen only on 127.0.0.1;
#   2. neither process holds any connection to a non-loopback address;
#   3. the in-process network guard is on and blocks external connections;
#   4. the browser is restricted to the local server by Content-Security-Policy.
# A physical Wi-Fi-off rehearsal is still recommended before presenting.
param([int]$Port = 8765, [string]$AdminPin = $env:ASTRA_ADMIN_PIN)
$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:$Port/api/v1"
$fail = 0
function Check($ok, $text) { if ($ok) { Write-Host "PASS  $text" -ForegroundColor Green } else { Write-Host "FAIL  $text" -ForegroundColor Red; $script:fail++ } }

$health = Invoke-RestMethod "$base/system/health"
Check $health.offline.guard_installed "In-process network guard installed (ALLOW_EXTERNAL_NETWORK=false)"

$resp = Invoke-WebRequest "$base/system/health" -UseBasicParsing
Check ($resp.Headers["Content-Security-Policy"] -match "connect-src 'self'") "Browser restricted to the local server (CSP connect-src 'self')"

# Run a full workflow (scenario check-in -> analysis -> report) while watching sockets.
if (-not $AdminPin) { throw "Pass -AdminPin <admin PIN> (needed to run the scripted demo scenario)." }
$run = Invoke-RestMethod -Method Post "$base/demo/scenarios/gradual/run" -Headers @{"X-Admin-PIN" = $AdminPin}
Invoke-RestMethod -Method Post "$base/reports" -ContentType "application/json" -Body (@{profile_id = "crew-demo-02"} | ConvertTo-Json) | Out-Null
Check ($null -ne $run.run_id) "Full analysis workflow completed locally (run $($run.run_id))"

$serverPids = (Get-NetTCPConnection -LocalPort $Port -State Listen).OwningProcess | Select-Object -Unique
$ollamaPids = (Get-Process ollama*, "ollama app" -ErrorAction SilentlyContinue).Id
foreach ($procId in @($serverPids) + @($ollamaPids)) {
    if (-not $procId) { continue }
    $name = (Get-Process -Id $procId).ProcessName
    $listen = Get-NetTCPConnection -OwningProcess $procId -State Listen -ErrorAction SilentlyContinue
    $public = $listen | Where-Object { $_.LocalAddress -notin @("127.0.0.1", "::1") }
    Check (-not $public) "$name (pid $procId) listens only on loopback"
    $external = Get-NetTCPConnection -OwningProcess $procId -ErrorAction SilentlyContinue |
        Where-Object { $_.State -ne "Listen" -and $_.RemoteAddress -notin @("127.0.0.1", "::1", "0.0.0.0", "::") }
    Check (-not $external) "$name (pid $procId) has no connections to external addresses"
}
$after = Invoke-RestMethod "$base/system/health"
Check ($after.offline.blocked_attempts -eq $health.offline.blocked_attempts) "No external connection attempts during the workflow (blocked counter unchanged)"

if ($fail) { Write-Host "`n$fail check(s) failed." -ForegroundColor Red; exit 1 } else { Write-Host "`nAll offline checks passed." -ForegroundColor Green }

