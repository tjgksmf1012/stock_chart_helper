param(
    [string]$ApiBaseUrl = "https://stock-chart-helper-api.onrender.com",
    [string]$FrontendUrl = "https://frontend-mu-sooty-i4662dxm4r.vercel.app"
)

$ErrorActionPreference = "Stop"

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Url,
        [int]$TimeoutSec = 30
    )

    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    Write-Host $Url

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
        Write-Host "HTTP $($response.StatusCode)" -ForegroundColor Green

        $contentType = $response.Headers["Content-Type"]
        if ($contentType -and $contentType -notmatch "json" -and $Url -match "/api/|/health") {
            Write-Host "Warning: API endpoint did not return JSON. Content-Type: $contentType" -ForegroundColor Yellow
        }

        $body = $response.Content
        if ($body.Length -gt 500) {
            $body = $body.Substring(0, 500) + "..."
        }
        Write-Host $body
        return $true
    }
    catch {
        $statusCode = $null
        if ($_.Exception.Response) {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }

        if ($statusCode) {
            Write-Host "HTTP $statusCode" -ForegroundColor Red
        } else {
            Write-Host "Request failed" -ForegroundColor Red
        }

        Write-Host $_.Exception.Message -ForegroundColor Red

        if ($statusCode -eq 502 -and $Url -match "onrender.com") {
            Write-Host "Render is returning 502. If the response header contains x-render-routing: no-deploy, the backend service has no active deploy or is pointed at the wrong Render service." -ForegroundColor Yellow
        }
        return $false
    }
}

$api = $ApiBaseUrl.TrimEnd("/")
$frontend = $FrontendUrl.TrimEnd("/")

Write-Host "Stock Chart Helper deployment check" -ForegroundColor White
Write-Host "Frontend: $frontend"
Write-Host "API:      $api"

$frontendOk = Test-Endpoint -Name "Frontend shell" -Url $frontend -TimeoutSec 20
$healthOk = Test-Endpoint -Name "Backend health" -Url "$api/health" -TimeoutSec 30
$statusOk = Test-Endpoint -Name "Backend system status" -Url "$api/api/v1/system/status" -TimeoutSec 30
$dashboardOk = Test-Endpoint -Name "Dashboard sample data" -Url "$api/api/v1/dashboard/overview?timeframe=1d&limit=3" -TimeoutSec 45
$aiOk = Test-Endpoint -Name "AI recommendations" -Url "$api/api/v1/ai/recommendations?timeframe=1d&limit=3" -TimeoutSec 45
$frontendProxyOk = Test-Endpoint -Name "Frontend API proxy" -Url "$frontend/api/v1/system/status" -TimeoutSec 45

Write-Host ""
Write-Host "Summary" -ForegroundColor Cyan
Write-Host "Frontend shell:        $(if ($frontendOk) { 'OK' } else { 'FAIL' })"
Write-Host "Backend health:        $(if ($healthOk) { 'OK' } else { 'FAIL' })"
Write-Host "Backend system status: $(if ($statusOk) { 'OK' } else { 'FAIL' })"
Write-Host "Dashboard sample data: $(if ($dashboardOk) { 'OK' } else { 'FAIL' })"
Write-Host "AI recommendations:    $(if ($aiOk) { 'OK' } else { 'FAIL' })"
Write-Host "Frontend API proxy:    $(if ($frontendProxyOk) { 'OK' } else { 'FAIL' })"

if (-not $healthOk) {
    Write-Host ""
    Write-Host "Most likely fix: deploy the backend successfully, then set Vercel VITE_API_BASE_URL to the active backend origin and redeploy the frontend." -ForegroundColor Yellow
    exit 1
}

if (-not $statusOk -or -not $dashboardOk -or -not $aiOk -or -not $frontendProxyOk) {
    exit 2
}
