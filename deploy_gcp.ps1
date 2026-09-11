# GPF-SmartInvestor-AI - Google Cloud Run Deployment Script (PowerShell)
$ErrorActionPreference = "Stop"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  GPF-SmartInvestor-AI - Google Cloud Run Deployment Script" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check gcloud CLI
$gcloudCmd = Get-Command gcloud -ErrorAction SilentlyContinue
if (-not $gcloudCmd) {
    Write-Host "[ERROR] gcloud CLI was not found on your system." -ForegroundColor Red
    Write-Host "Please download and install Google Cloud SDK from:" -ForegroundColor Yellow
    Write-Host "https://cloud.google.com/sdk/docs/install" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit..."
    exit 1
}

# 2. Get or set GCP Project ID
$gcpProject = ""
try {
    $rawProj = (gcloud config get-value project 2>$null)
    if ($rawProj) {
        $gcpProject = $rawProj.Trim()
    }
} catch {}

if ([string]::IsNullOrWhiteSpace($gcpProject) -or $gcpProject -eq "(unset)") {
    $gcpProject = "gorpf-505806"
    gcloud config set project $gcpProject
}

$region = "asia-southeast1"
Write-Host "[*] Active GCP Project: $gcpProject" -ForegroundColor Green
Write-Host "[*] Target Region:      $region (Singapore)" -ForegroundColor Green
Write-Host ""

# 3. Enable Required Google Cloud APIs
Write-Host "[*] Enabling required Google Cloud APIs (Cloud Run, Scheduler, Build)..." -ForegroundColor Yellow
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com --project $gcpProject

# 4. Read .env file variables
$envVars = @{}
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $key = $parts[0].Trim()
            $val = $parts[1].Trim()
            $envVars[$key] = $val
        }
    }
}

$spreadsheetId = if ($envVars.ContainsKey("SPREADSHEET_ID")) { $envVars["SPREADSHEET_ID"] } else { "" }
$geminiApiKey = if ($envVars.ContainsKey("GEMINI_API_KEY")) { $envVars["GEMINI_API_KEY"] } else { "" }
$lineToken = if ($envVars.ContainsKey("LINE_CHANNEL_ACCESS_TOKEN")) { $envVars["LINE_CHANNEL_ACCESS_TOKEN"] } else { "" }
$lineSecret = if ($envVars.ContainsKey("LINE_CHANNEL_SECRET")) { $envVars["LINE_CHANNEL_SECRET"] } else { "" }
$tgToken = if ($envVars.ContainsKey("TELEGRAM_BOT_TOKEN")) { $envVars["TELEGRAM_BOT_TOKEN"] } else { "" }
$tgChatId = if ($envVars.ContainsKey("TELEGRAM_CHAT_ID")) { $envVars["TELEGRAM_CHAT_ID"] } else { "" }

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  STEP 1: Deploy Backend (FastAPI) to Cloud Run" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

$geminiModel = if ($envVars.ContainsKey("GEMINI_MODEL")) { $envVars["GEMINI_MODEL"] } else { "gemini-3.6-flash" }

$backendEnvString = "PORT=8080,HOST=0.0.0.0,RELOAD=false,SPREADSHEET_ID=$spreadsheetId,GEMINI_API_KEY=$geminiApiKey,GEMINI_MODEL=$geminiModel,LINE_CHANNEL_ACCESS_TOKEN=$lineToken,LINE_CHANNEL_SECRET=$lineSecret,TELEGRAM_BOT_TOKEN=$tgToken,TELEGRAM_CHAT_ID=$tgChatId"

Write-Host "[*] Building and deploying backend image..." -ForegroundColor Yellow
gcloud run deploy gpf-backend `
    --source . `
    --region $region `
    --platform managed `
    --allow-unauthenticated `
    --port 8080 `
    --memory 512Mi `
    --cpu 1 `
    --set-env-vars $backendEnvString

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[ERROR] Backend deployment failed." -ForegroundColor Red
    Write-Host "If the error mentions 'Billing account not found':" -ForegroundColor Yellow
    Write-Host "Please enable billing for project '$gcpProject' at: https://console.cloud.google.com/billing/linkedaccount?project=$gcpProject" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit..."
    exit 1
}

$rawUrl = (gcloud run services describe gpf-backend --platform managed --region $region --format="value(status.url)" 2>$null)
if (-not $rawUrl) {
    Write-Host "[ERROR] Could not retrieve Backend URL." -ForegroundColor Red
    exit 1
}
$backendUrl = $rawUrl.Trim()
Write-Host ""
Write-Host "[SUCCESS] Backend Deployed: $backendUrl" -ForegroundColor Green
Write-Host ""

Write-Host "[*] Registering Telegram Bot Webhook..." -ForegroundColor Yellow
try {
    $whRes = Invoke-RestMethod -Uri "$backendUrl/api/telegram/set-webhook?url=$backendUrl" -Method Get -TimeoutSec 10 -ErrorAction SilentlyContinue
    if ($whRes.ok) {
        Write-Host "[SUCCESS] Telegram Webhook registered successfully with @Gor_Gpf_bot!" -ForegroundColor Green
    }
} catch {}
Write-Host ""


Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  STEP 2: Setup Google Cloud Scheduler (Cron Jobs)" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[*] Setting up Job: Daily Market Sync (18:30 Mon-Fri)..." -ForegroundColor Yellow
$null = gcloud scheduler jobs create http gpf-daily-sync `
    --location $region `
    --schedule="30 18 * * 1-5" `
    --time-zone="Asia/Bangkok" `
    --uri="$backendUrl/api/trigger-sync" `
    --http-method=POST 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud scheduler jobs update http gpf-daily-sync --location $region --uri="$backendUrl/api/trigger-sync"
}

Write-Host "[*] Setting up Job: Real-time Check (Hourly 10:00-17:00 Mon-Fri)..." -ForegroundColor Yellow
$null = gcloud scheduler jobs create http gpf-realtime-check `
    --location $region `
    --schedule="0 10-17 * * 1-5" `
    --time-zone="Asia/Bangkok" `
    --uri="$backendUrl/api/trigger-realtime" `
    --http-method=POST 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud scheduler jobs update http gpf-realtime-check --location $region --uri="$backendUrl/api/trigger-realtime"
}

Write-Host "[*] Setting up Job: Saturday Weekly Alerts (10:00 Saturday)..." -ForegroundColor Yellow
$null = gcloud scheduler jobs create http gpf-weekly-alerts `
    --location $region `
    --schedule="0 10 * * 6" `
    --time-zone="Asia/Bangkok" `
    --uri="$backendUrl/api/trigger-weekly" `
    --http-method=POST 2>$null
if ($LASTEXITCODE -ne 0) {
    gcloud scheduler jobs update http gpf-weekly-alerts --location $region --uri="$backendUrl/api/trigger-weekly"
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  STEP 3: Deploy Frontend (Next.js) to Cloud Run" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

Push-Location "frontend"
Write-Host "[*] Building and deploying frontend image..." -ForegroundColor Yellow
gcloud run deploy gpf-frontend `
    --source . `
    --region $region `
    --platform managed `
    --allow-unauthenticated `
    --port 3000 `
    --memory 512Mi `
    --cpu 1 `
    --set-env-vars "NEXT_PUBLIC_API_URL=$backendUrl"

$frontendUrl = (gcloud run services describe gpf-frontend --platform managed --region $region --format="value(status.url)").Trim()
Pop-Location

Write-Host "[*] Linking Frontend Dashboard URL to Backend Notifier..." -ForegroundColor Yellow
gcloud run services update gpf-backend --region $region --platform managed --update-env-vars "DASHBOARD_URL=$frontendUrl" 2>$null

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "  DEPLOYMENT COMPLETED SUCCESSFULLY!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "  - Frontend Dashboard: $frontendUrl" -ForegroundColor Cyan
Write-Host "  - Backend API:        $backendUrl" -ForegroundColor Cyan
Write-Host "  - API Docs (Swagger): $backendUrl/docs" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""
Read-Host "Press Enter to exit..."
