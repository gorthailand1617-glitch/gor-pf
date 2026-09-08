# 🏛️ Gor.PF (GPF-SmartInvestor-AI): Enterprise Architecture & Security Specification

เอกสารข้อกำหนดสถาปัตยกรรมระบบ ความปลอดภัยของข้อมูล และคู่มือการปฏิบัติการระดับสถาบันการเงิน (Institutional-Grade Technical Whitepaper & Operator Guide)

---

## 1. ภาพรวมสถาปัตยกรรมระบบ (System Architecture Overview)

Gor.PF ได้รับการออกแบบภายใต้สถาปัตยกรรม **Hybrid Fault-Tolerant Microservices** โดยแยกส่วนการประมวลผลโมเดลเชิงปริมาณ (Quant Engine), การดึงและสอบทานข้อมูล (Data Pipeline), ฐานข้อมูลทนทานสูง (Dual-Driver Storage), และส่วนติดต่อผู้ใช้งาน (Web Dashboard & Telegram Interface):

```mermaid
graph TD
    subgraph Market Data Layer
        YF[Yahoo Finance Proxy API<br>SPY, BND, EEM, GLD, SET]
        FX[Bank of Thailand / FX Feed<br>THB=X Rate & 30d Volatility]
    end

    subgraph Core Orchestration & Quant Engine
        NAV[GPF NAV Synchronizer<br>Tracking Diff & Settlement Reconciliation]
        DYN_FX[Dynamic Hedging Engine<br>Trend + Volatility Z-Score Filter]
        GLIDE[Continuous Smooth Glide Path<br>Sequence-of-Returns Risk Mitigator]
        QUANT[Multi-Factor Quant Engine<br>RSI + MACD + EMA Trend Filters]
        LLM[Explainable AI Validator<br>Gemini Sentiment & Risk Guardrail]
    end

    subgraph Security & Storage Layer
        WAL[(SQLite WAL Mode<br>Sub-millisecond ACID Local DB)]
        POSTGRES[(Google Cloud SQL PostgreSQL<br>Multi-Node Scalability Driver)]
        CHAIN[SHA-256 Hash Chaining<br>Tamper-Evident Immutable Audit Log]
        GSHEETS[(Google Sheets Mirror<br>Human-Facing Executive Dashboard)]
    end

    subgraph Presentation & Interaction Layer
        NEXT[Next.js 16.3 Production App<br>Turbopack + Tailwind Design]
        TG_BOT[Interactive Telegram Bot<br>@Gor_Gpf_bot Multi-User Hub]
        LINE_BOT[LINE Official Bot<br>Push Alerts & Signals]
    end

    Market Data Layer --> Core Orchestration & Quant Engine
    Core Orchestration & Quant Engine --> Security & Storage Layer
    Security & Storage Layer --> Presentation & Interaction Layer
```

---

## 2. เสาหลักทางคณิตศาสตร์และการเงิน (Mathematical Formulations)

### 2.1 Continuous Smooth Glide Path (ขจัด Cliff Effect)
เพื่อป้องกันปัญหาการกระชากพอร์ตจากการขายสินทรัพย์เสี่ยงทิ้งแบบขั้นบันไดเมื่ออายุข้ามเกณฑ์ ระบบได้ปรับใช้สมการ **Smooth Linear Transition**:

$$E_{cap}(age) = E_{max} - (E_{max} - E_{min}) \times \left( \frac{\max(0, \min(age - 35, 25))}{25} \right)$$

- **ช่วงอายุ $\le 35$ ปี:** อนุญาตสัดส่วนหุ้นสูงสุด $E_{max}$ (70% สำหรับ Moderate, 80% สำหรับ Aggressive)
- **ช่วงอายุ $\ge 60$ ปี:** ควบคุมเพดานหุ้นเหลือ $E_{min}$ (20% เพื่อขจัด Sequence-of-Returns Risk)
- **ช่วงอายุ 35 ถึง 60 ปี:** สัดส่วนหุ้นจะทยอยปรับลดลงเฉลี่ยปีละ **$\approx 2.0\% - 2.4\%$** อย่างนุ่มนวลและสม่ำเสมอ

### 2.2 Transparent Dynamic FX Hedging Model
การกำหนดสัดส่วนการป้องกันความเสี่ยงค่าเงิน (Hedge Ratio: $h$) ของสินทรัพย์ต่างประเทศ อิงตามสูตรคณิตศาสตร์ที่โปร่งใสและตรวจสอบได้:

1. **Trend Trigger ($USD/THB$ vs $MA60$):**
   - หาก $Spot < MA60$ (เงินบาทมีแนวโน้มแข็งค่าต่อเนื่อง): ปรับ $h = 0.75$ (75%) ทันที เพื่อล็อคผลตอบแทนและป้องกัน Foreign Currency Drag
   - หาก $Spot \ge MA60$ (เงินบาทมีแนวโน้มอ่อนค่า): ปรับ $h = 0.50$ (50%) เพื่อรับกำไรจากค่าเงินดอลลาร์โดยไม่ต้องจ่ายต้นทุน Forward Premium
2. **Volatility Z-Score Trigger:**
   $$Z_{vol} = \frac{\sigma_{30d} - \bar{\sigma}_{1y}}{\text{Std}(\sigma_{1y})}$$
   - หาก $Z_{vol} > 1.5$ (ความผันผวนค่าเงินพุ่งสูงผิดปกติ): เพิ่ม $h$ ขึ้นอีก $+5\%$ (สูงสุดไม่เกิน $80\%$) เพื่อจำกัดความเสี่ยงเชิงระบบ

### 2.3 Cryptographic SHA-256 Hash Chaining
ประวัติคำสั่งปรับพอร์ต (`rebalance_logs`) ทุกรายการได้รับการรับรองความถูกต้องด้วย Cryptographic Hash Chain:

$$\text{EntryHash}_n = \text{SHA256}(\text{EntryHash}_{n-1} \parallel \text{Timestamp} \parallel \text{UserID} \parallel \text{RebalanceNo} \parallel \text{ScoreBefore} \parallel \text{ScoreAfter} \parallel \text{Weights} \parallel \text{Reason})$$

- ทุกรายการเชื่อมโยงกับแฮชของรายการก่อนหน้า
- หากมีผู้ใดแอบแก้ไขข้อมูลในฐานข้อมูล แม้แต่ตัวอักษรเดียว หรือทศนิยมตำแหน่งเดียว แฮชของรายการถัดไปจะแตกหักทันที
- สามารถตรวจสอบความถูกต้องได้ทุกเวลาผ่าน Endpoint: `GET /api/audit/verify`

---

## 3. สถาปัตยกรรมจัดเก็บข้อมูลแบบ Dual-Driver (Scalability Roadmap)

```text
               ┌───────────────────────────────┐
               │     StorageProvider Core      │
               └───────────────┬───────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            ▼                                     ▼
┌───────────────────────┐             ┌────────────────────────┐
│  Driver 1: SQLite WAL │             │ Driver 2: PostgreSQL   │
│  (Default / On-Prem)  │             │ (Google Cloud SQL)     │
│  - Sub-ms latency     │             │ - Multi-instance scale │
│  - Zero dependencies  │             │ - High concurrency     │
│  - Local thread-safe  │             │ - Production failover  │
└───────────────────────┘             └────────────────────────┘
```

- **โหมด Single-node / Local:** ใช้ SQLite WAL Mode (`data/gorpf_governance.db`) ตอบสนอง < 1ms
- **โหมด Multi-node Cloud Run:** เพียงกำหนดค่าตัวแปร `DATABASE_URL=postgresql://user:pass@cloudsql/gorpf` ใน Cloud Run Environment ระบบจะสลับไปใช้ Connection Pool ของ PostgreSQL ทันที โดยไม่ต้องแก้โค้ดแม้แต่บรรทัดเดียว

---

## 4. คู่มือการใช้งานและคำสั่งระบบ (Operator Guide)

### 4.1 คำสั่งโต้ตอบผ่าน Telegram Bot (@Gor_Gpf_bot)
| คำสั่ง (Command) | คำอธิบายการทำงาน |
| :--- | :--- |
| `/start` หรือ `/subscribe` | ลงทะเบียนรับแจ้งเตือนสัญญาณการลงทุนอัตโนมัติ (บันทึกลงระบบทันที) |
| `/check` หรือ `/status` | ตรวจสอบสถานะการทำงานของระบบ แหล่งข้อมูล และเวลาอัปเดตล่าสุด |
| `/quota` | ตรวจสอบโควตาการปรับพอร์ตปีปัจจุบัน (ใช้ไปกี่ครั้ง / เหลือสิทธิ์กี่ครั้ง จาก 12 ครั้ง) |
| `/opportunity` | ตรวจสอบโอกาสการปรับพอร์ตเพื่อเพิ่มผลตอบแทน ณ ปัจจุบัน |
| `/sync` | สั่งให้ระบบดึงราคาและคำนวณสัญญาณทางเทคนิครอบล่าสุดทันที |
| `/help` | แสดงรายการคำสั่งทั้งหมดและวิธีใช้งาน |

### 4.2 การตรวจสอบสุขภาพระบบ (Enterprise Observability)
สามารถเรียกดูสถานะ Telemetry แบบ Real-time ผ่าน:
```bash
curl http://localhost:8008/api/health
```
**ตัวอย่างผลลัพธ์ (JSON):**
```json
{
  "status": "HEALTHY",
  "timestamp": "2026-09-03T15:28:00.123456",
  "database": {
    "engine": "SQLite WAL Mode (ACID)",
    "latency_ms": 0.42,
    "status": "CONNECTED"
  },
  "audit_trail": {
    "integrity_verified": true,
    "latest_hash": "a4f8e9102c17b...",
    "total_entries": 12
  },
  "fx_service": {
    "spot_usd_thb": 34.50,
    "status": "OPERATIONAL"
  },
  "google_sheets_sync": {
    "connected": true,
    "status": "CONNECTED"
  }
}
```

---

## 5. สรุปผลการทดสอบเชิงคุณภาพ (Test Assurance)
- **Pytest Suite:** 30 ผ่านทั้งหมดจาก 30 รายการ (100% Success)
- **Coverage Areas:** Dynamic Hedging, Smooth Glide Path, SHA-256 Hash Chain Tamper Detection, Edge Cases, Multi-regime Backtesting
- **Next.js Production Build:** 0 Typescript Errors, Turbopack Optimized Prerendered Static Pages
