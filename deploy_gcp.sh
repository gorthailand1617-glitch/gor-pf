#!/bin/bash
set -e

echo "======================================================================"
echo "  GPF-SmartInvestor-AI - Google Cloud Run Deployment Script"
echo "======================================================================"
echo ""

# 1. Check gcloud CLI
if ! command -v gcloud &> /dev/null; then
    echo "[ERROR] gcloud CLI not found. Please install Google Cloud SDK."
    exit 1
fi

# 2. Get Project ID
GCP_PROJECT=$(gcloud config get-value project 2>/dev/null)
if [ -z "$GCP_PROJECT" ]; then
    read -p "Enter Google Cloud Project ID: " GCP_PROJECT
    gcloud config set project "$GCP_PROJECT"
fi

REGION="asia-southeast1"
echo "[*] Using Project: $GCP_PROJECT"
echo "[*] Region: $REGION (Singapore)"
echo ""

# 3. Enable Required APIs
echo "[*] Enabling required APIs..."
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com --project "$GCP_PROJECT"

# 4. Load .env if present
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

echo ""
echo "======================================================================"
echo "  STEP 1: Deploy Backend (FastAPI) to Cloud Run"
echo "======================================================================"
echo ""

gcloud run deploy gpf-backend \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --port 8080 \
    --memory 512Mi \
    --cpu 1 \
    --set-env-vars "PORT=8080,HOST=0.0.0.0,SPREADSHEET_ID=${SPREADSHEET_ID:-},GEMINI_API_KEY=${GEMINI_API_KEY:-},LINE_CHANNEL_ACCESS_TOKEN=${LINE_CHANNEL_ACCESS_TOKEN:-},LINE_CHANNEL_SECRET=${LINE_CHANNEL_SECRET:-},TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-},TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID:-}"

BACKEND_URL=$(gcloud run services describe gpf-backend --platform managed --region "$REGION" --format="value(status.url)")
echo ""
echo "[SUCCESS] Backend Deployed: $BACKEND_URL"
echo ""

echo "======================================================================"
echo "  STEP 2: Setup Cloud Scheduler Cron Jobs"
echo "======================================================================"
echo ""

# Daily sync
gcloud scheduler jobs create http gpf-daily-sync \
    --location "$REGION" \
    --schedule="30 18 * * 1-5" \
    --time-zone="Asia/Bangkok" \
    --uri="$BACKEND_URL/api/trigger-sync" \
    --http-method=POST 2>/dev/null || gcloud scheduler jobs update http gpf-daily-sync --location "$REGION" --uri="$BACKEND_URL/api/trigger-sync"

# Realtime check
gcloud scheduler jobs create http gpf-realtime-check \
    --location "$REGION" \
    --schedule="0 10-17 * * 1-5" \
    --time-zone="Asia/Bangkok" \
    --uri="$BACKEND_URL/api/trigger-realtime" \
    --http-method=POST 2>/dev/null || gcloud scheduler jobs update http gpf-realtime-check --location "$REGION" --uri="$BACKEND_URL/api/trigger-realtime"

# Weekly Saturday alerts
gcloud scheduler jobs create http gpf-weekly-alerts \
    --location "$REGION" \
    --schedule="0 10 * * 6" \
    --time-zone="Asia/Bangkok" \
    --uri="$BACKEND_URL/api/trigger-weekly" \
    --http-method=POST 2>/dev/null || gcloud scheduler jobs update http gpf-weekly-alerts --location "$REGION" --uri="$BACKEND_URL/api/trigger-weekly"

echo ""
echo "======================================================================"
echo "  STEP 3: Deploy Frontend (Next.js) to Cloud Run"
echo "======================================================================"
echo ""

cd frontend
gcloud run deploy gpf-frontend \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --port 3000 \
    --memory 512Mi \
    --cpu 1 \
    --set-env-vars "NEXT_PUBLIC_API_URL=$BACKEND_URL"

FRONTEND_URL=$(gcloud run services describe gpf-frontend --platform managed --region "$REGION" --format="value(status.url)")
cd ..

echo ""
echo "======================================================================"
echo "  🎉 DEPLOYMENT COMPLETED SUCCESSFULLY!"
echo "======================================================================"
echo " - Frontend Dashboard: $FRONTEND_URL"
echo " - Backend API:        $BACKEND_URL"
echo " - API Docs (Swagger): $BACKEND_URL/docs"
echo "======================================================================"
