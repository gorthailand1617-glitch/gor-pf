# 🚀 คู่มือการนำ GPF-SmartInvestor-AI ขึ้น Google Cloud (Cloud Run)

คู่มือนี้จะพาคุณนำระบบ **GPF-SmartInvestor-AI (Gor.PF)** ขึ้นสู่ **Google Cloud Platform (GCP)** โดยใช้ **Google Cloud Run** (Serverless Container) และ **Google Cloud Scheduler** (ระบบตั้งเวลารันอัตโนมัติ) เพื่อให้ระบบทำงานได้ตลอด 24/7 โดยแทบไม่มีค่าใช้จ่าย (อยู่ในขอบเขต Free Tier)

---

## 📋 สรุปสถาปัตยกรรมระบบบน Google Cloud

```
                         ┌─────────────────────────────┐
                         │   Google Cloud Scheduler    │
                         │ (รัน 18:30 น. & ทุกวันเสาร์)│
                         └──────────────┬──────────────┘
                                        │ HTTP POST
                                        ▼
┌─────────────────────────┐      ┌─────────────────────────────┐      ┌───────────────────────┐
│   Google Cloud Run      │ ───► │      Google Cloud Run       │ ───► │ Google Sheets & Drive │
│  (Next.js Frontend)     │      │      (FastAPI Backend)      │      │     (Data Storage)    │
└─────────────────────────┘      └──────────────┬──────────────┘      └───────────────────────┘
                                                │
                                                ├───────────────────►  Gemini 1.5/2.0 Flash
                                                ├───────────────────►  LINE Messaging API
                                                └───────────────────►  Telegram Bot API
```

---

## 🛠️ สิ่งที่ต้องเตรียมก่อนเริ่ม (Prerequisites)

1. **บัญชี Google Cloud Platform (GCP):**
   - ไปที่ [Google Cloud Console](https://console.cloud.google.com/)
   - สร้าง Project ใหม่ (เช่น `gpf-smartinvestor-ai`)
2. **Google Cloud SDK (`gcloud` CLI) หรือใช้ Cloud Shell:**
   - **ทางเลือก A (ง่ายที่สุด - ทำในเว็บ):** เปิด [Google Cloud Shell](https://shell.cloud.google.com/) ในเบราว์เซอร์ (มี `gcloud`, `git`, `docker` ติดตั้งพร้อมใช้งานทันที)
   - **ทางเลือก B (ทำจากคอมพิวเตอร์ของคุณ):** ดาวน์โหลดและติดตั้ง [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) แล้วสั่ง `gcloud auth login`

---

## ⚡ วิธีที่ 1: Deploy อัตโนมัติแบบ 1-Click (แนะนำ)

### สำหรับ Windows:
1. ดับเบิลคลิกไฟล์ `deploy_gcp.bat` หรือเปิด Terminal/Command Prompt แล้วพิมพ์:
   ```cmd
   deploy_gcp.bat
   ```
2. สคริปต์จะทำการ:
   - ตรวจสอบ Project ID และเปิดใช้งาน Cloud Run / Scheduler APIs
   - ดึงค่า Config จาก `.env` ไปตั้งค่าใน Cloud Run
   - Build & Deploy Backend (FastAPI) ขึ้น Cloud Run
   - สร้าง Cloud Scheduler Jobs ทั้งหมดให้โดยอัตโนมัติ
   - Build & Deploy Frontend (Next.js) ขึ้น Cloud Run และเชื่อมต่อกับ Backend อัตโนมัติ

### สำหรับ Linux / macOS / Google Cloud Shell:
```bash
chmod +x deploy_gcp.sh
./deploy_gcp.sh
```

---

## 🧩 วิธีที่ 2: Deploy ด้วยตนเองทีละขั้นตอน (Manual Step-by-Step)

### ขั้นตอนที่ 1: ล็อกอินและเปิดใช้ APIs ที่จำเป็น
```bash
# 1. Login
gcloud auth login

# 2. เลือก Project ที่ต้องการ
gcloud config set project YOUR_PROJECT_ID

# 3. เปิดใช้งาน APIs
gcloud services enable run.googleapis.com \
    cloudscheduler.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com
```

---

### ขั้นตอนที่ 2: Deploy Backend (FastAPI)
```bash
gcloud run deploy gpf-backend \
    --source . \
    --region asia-southeast1 \
    --platform managed \
    --allow-unauthenticated \
    --port 8080 \
    --memory 512Mi \
    --cpu 1 \
    --set-env-vars "PORT=8080,HOST=0.0.0.0,SPREADSHEET_ID=YOUR_SPREADSHEET_ID,GEMINI_API_KEY=YOUR_GEMINI_KEY,LINE_CHANNEL_ACCESS_TOKEN=YOUR_LINE_TOKEN,LINE_CHANNEL_SECRET=YOUR_LINE_SECRET,TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_TOKEN,TELEGRAM_CHAT_ID=YOUR_TELEGRAM_CHAT_ID"
```
> 💡 *เมื่อ Deploy เสร็จ คุณจะได้รับ URL เช่น `https://gpf-backend-xxxxx-as.a.run.app`*

---

### ขั้นตอนที่ 3: ตั้งค่า Google Cloud Scheduler (รันคำนวณและแจ้งเตือนอัตโนมัติ)

ให้แทนที่ `YOUR_BACKEND_URL` ด้วย URL ที่ได้จากขั้นตอนที่ 2:

1. **Daily Market Sync (รันทุกวันจันทร์-ศุกร์ เวลา 18:30 น.):**
   ```bash
   gcloud scheduler jobs create http gpf-daily-sync \
       --location asia-southeast1 \
       --schedule="30 18 * * 1-5" \
       --time-zone="Asia/Bangkok" \
       --uri="YOUR_BACKEND_URL/api/trigger-sync" \
       --http-method=POST
   ```

2. **Real-time Intraday Check (เช็คตลาดทุก 1 ชั่วโมง เวลา 10:00-17:00 น. วันจันทร์-ศุกร์):**
   ```bash
   gcloud scheduler jobs create http gpf-realtime-check \
       --location asia-southeast1 \
       --schedule="0 10-17 * * 1-5" \
       --time-zone="Asia/Bangkok" \
       --uri="YOUR_BACKEND_URL/api/trigger-realtime" \
       --http-method=POST
   ```

3. **Weekly / Monthly Alerts (แจ้งผลกำไร-ขาดทุน และเตือนปรับพอร์ต ทุกวันเสาร์ 10:00 น.):**
   ```bash
   gcloud scheduler jobs create http gpf-weekly-alerts \
       --location asia-southeast1 \
       --schedule="0 10 * * 6" \
       --time-zone="Asia/Bangkok" \
       --uri="YOUR_BACKEND_URL/api/trigger-weekly" \
       --http-method=POST
   ```

---

### ขั้นตอนที่ 4: Deploy Frontend (Next.js Dashboard)
```bash
cd frontend

gcloud run deploy gpf-frontend \
    --source . \
    --region asia-southeast1 \
    --platform managed \
    --allow-unauthenticated \
    --port 3000 \
    --memory 512Mi \
    --cpu 1 \
    --set-env-vars "NEXT_PUBLIC_API_URL=YOUR_BACKEND_URL"

cd ..
```
> 💡 *เมื่อ Deploy เสร็จ คุณจะได้รับ URL ของ Frontend Dashboard เช่น `https://gpf-frontend-xxxxx-as.a.run.app`*

---

## 🔒 การจัดการ Google Service Account Credentials บน Cloud

เพื่อความปลอดภัยสูงสุดและไม่ต้องกังวลเรื่องไฟล์ `service_account.json` หลุด:

### วิธี A: นำข้อมูล JSON ใส่ลงใน Environment Variable โดยตรง
คุณสามารถคัดลอกเนื้อหาทั้งหมดในไฟล์ `service_account.json` (ให้อยู่ในบรรทัดเดียว) แล้วนำไปใส่ใน Environment Variable ชื่อ `GOOGLE_CREDENTIALS_JSON` ใน Cloud Run ได้ทันที:
```bash
# ตัวอย่างการตั้งค่าผ่าน gcloud
gcloud run services update gpf-backend \
    --region asia-southeast1 \
    --update-env-vars "GOOGLE_CREDENTIALS_JSON={\"type\":\"service_account\",\"project_id\":\"...\"}"
```

### วิธี B: ให้สิทธิ์ Default Compute Service Account ของ Cloud Run
1. ไปที่ **Google Cloud Console > IAM & Admin**
2. ค้นหา Service Account ของ Cloud Run (ลงท้ายด้วย `@developer.gserviceaccount.com` หรือ `...-compute@developer.gserviceaccount.com`)
3. นำอีเมลนี้ไป **แชร์สิทธิ์ Edit ใน Google Sheets** ของคุณ
4. ระบบจะสามารถเชื่อมต่อ Google Sheets ได้อัตโนมัติผ่าน Google Cloud Identity โดยไม่ต้องใช้ไฟล์คีย์ JSON เลย!

---

## 📲 การตั้งค่า LINE Webhook

1. เข้าไปที่ [LINE Developers Console](https://developers.line.biz/console/)
2. เลือก Channel ของคุณ แล้วไปที่แท็บ **Messaging API**
3. ที่หัวข้อ **Webhook settings**:
   - ใส่ **Webhook URL**: `https://YOUR_BACKEND_URL/api/line/webhook`
   - เปิดสวิตช์ **Use webhook** เป็น **ON**
   - กดปุ่ม **Verify** เพื่อทดสอบการเชื่อมต่อ (ควรขึ้น Success 200)

---

## 🔍 การดู Logs และตรวจสอบสถานะระบบ

- **ดู Logs ของ Backend:**
  ```bash
  gcloud run services logs tail gpf-backend --region asia-southeast1
  ```
- **ดู Logs ผ่านเบราว์เซอร์:**
  - ไปที่ [Google Cloud Run Console](https://console.cloud.google.com/run)
  - คลิกที่ Service `gpf-backend` หรือ `gpf-frontend`
  - ไปที่แท็บ **LOGS** เพื่อดูข้อความแบบ Real-time
