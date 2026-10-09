$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dashboardUrl = "http://localhost:8000/dashboard"
$legacyContainerIds = docker ps -aq --filter "name=legacy-v1-"
if ($legacyContainerIds) {
    docker rm -f $legacyContainerIds | Out-Null
}

docker compose --project-name eco-route --project-directory $projectRoot up --build -d --wait
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose failed with exit code $LASTEXITCODE"
}

for ($attempt = 1; $attempt -le 30; $attempt++) {
    try {
        $response = Invoke-WebRequest -Uri $dashboardUrl -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
            break
        }
    } catch {
        if ($attempt -eq 30) {
            throw "Dashboard did not become ready in time at $dashboardUrl"
        }

        Start-Sleep -Seconds 1
    }
}

Start-Process $dashboardUrl