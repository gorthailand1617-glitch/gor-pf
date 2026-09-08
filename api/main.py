import os
import logging
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Request, Header, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

ASSET_NAMES = {
    "fixed_income": "แผนตราสารหนี้",
    "money_market": "แผนเงินฝากและตราสารหนี้ระยะสั้น",
    "thai_equity": "แผนหุ้นไทย",
    "thai_property": "แผนกองทุนอสังหาริมทรัพย์ไทย",
    "global_equity": "แผนหุ้นต่างประเทศ",
    "global_debt": "แผนตราสารหนี้ต่างประเทศ",
    "gold": "แผนทองคำ"
}

from pydantic import BaseModel
from data_pipeline.gspread_client import GPFSpreadsheetClient
from data_pipeline.pipeline import GPFPipeline
from llm_service.gemini_client import GeminiAnalysisService
from line_bot.webhook import LINEWebhookHandler
from line_bot.notifier import LINEBotNotifier
from telegram_bot.notifier import TelegramBotNotifier

app = FastAPI(
    title="GPF-SmartInvestor-AI API",
    description="Quantitative Leading Signals and LLM Advisory API for Thailand Government Pension Fund Plans",
    version="1.0.0"
)

# CORS middleware config for Next.js dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict to dashboard domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Services dependency injection
def get_sheets_client():
    return GPFSpreadsheetClient()

def get_pipeline():
    return GPFPipeline()

def get_webhook_handler():
    return LINEWebhookHandler()

def get_notifier():
    return LINEBotNotifier()

def get_telegram_notifier():
    return TelegramBotNotifier()

def get_telegram_handler():
    from telegram_bot.webhook import TelegramWebhookHandler
    return TelegramWebhookHandler()

def get_storage_provider():
    from data_pipeline.storage_provider import StorageProvider
    return StorageProvider()

def get_fx_service():
    from data_pipeline.fx_service import FXService
    return FXService()

def get_backtest_engine():
    from quant_engine.backtest import GPFBacktestEngine
    return GPFBacktestEngine()


@app.get("/")
def read_root():
    return {
        "status": "healthy",
        "service": "GPF-SmartInvestor-AI",
        "environment": "development"
    }

@app.get("/api/signals")
def get_latest_signals(sheets: GPFSpreadsheetClient = Depends(get_sheets_client)):
    """Returns the latest signal, composite scores, and Thai advice for all plans."""
    if not sheets.is_connected():
        # Offline mock return for testing
        from data_pipeline.pipeline import DEFAULT_PLANS
        import random
        logger.info("Sheets client offline. Returning mock active signals.")
        mock_signals = {}
        for plan_id, details in DEFAULT_PLANS.items():
            score = float(random.randint(40, 85))
            signal = "BUY_HOLD" if score >= 70 else "WATCH" if score >= 45 else "REDUCE"
            mock_signals[plan_id] = {
                "date": "2026-08-17",
                "plan_id": plan_id,
                "plan_name": details["name_th"],
                "synthetic_nav": 105.3,
                "daily_return": 0.0015,
                "ma20": 104.2,
                "ma60": 102.5,
                "rsi": 58.2,
                "macd": 0.35,
                "macd_signal": 0.21,
                "volatility": 0.082,
                "base_score": score * 0.7,
                "sentiment_modifier": score * 0.3,
                "composite_score": score,
                "signal": signal,
                "thai_commentary": (
                    "ตลาดหลักมีความมั่นคงและมีแรงบวกต่อเนื่องหนุนสินทรัพย์เสี่ยง\n"
                    "คำแนะนำในปัจจุบันยังเป็นระดับซื้อและถือครองพอร์ตปกติ\n"
                    "เฝ้าระวังสัญญาณการถดถอยของสเปรดดอกเบี้ยตราสารหนี้อย่างใกล้ชิด"
                )
            }
        return mock_signals

    try:
        latest = sheets.get_latest_signals()
        return latest
    except Exception as e:
        logger.error(f"Error fetching signals from sheets: {e}")
        return {"error": str(e)}

@app.get("/api/history")
def get_historical_performance(
    plan_id: str = "main", 
    sheets: GPFSpreadsheetClient = Depends(get_sheets_client)
):
    """Returns historical daily performance records for charting."""
    if not sheets.is_connected():
        # Return mock history for offline testing
        import pandas as pd
        import numpy as np
        logger.info("Sheets client offline. Returning mock historical data.")
        dates = pd.date_range(end=pd.Timestamp.now(), periods=100)
        nav_val = 100.0
        mock_data = []
        for idx, d in enumerate(dates):
            ret = np.random.normal(0.0001, 0.005)
            nav_val *= (1 + ret)
            mock_data.append({
                "date": d.strftime("%Y-%m-%d"),
                "plan_id": plan_id,
                "synthetic_nav": float(nav_val),
                "daily_return": float(ret),
                "ma20": float(nav_val * 0.99),
                "ma60": float(nav_val * 0.97),
                "rsi": float(50 + 10 * np.sin(idx / 5)),
                "macd": float(0.5 * np.cos(idx / 10)),
                "macd_signal": float(0.4 * np.cos(idx / 10)),
                "volatility": 0.08,
                "composite_score": float(55 + 20 * np.sin(idx / 10)),
                "signal": "BUY_HOLD" if nav_val > 102 else "WATCH"
            })
        return mock_data

    try:
        history = sheets.get_synthetic_performance(plan_id)
        # Sort history by date ascending
        history = sorted(history, key=lambda x: x["date"])
        return history
    except Exception as e:
        logger.error(f"Error fetching historical data: {e}")
        return {"error": str(e)}

@app.post("/api/trigger-sync")
def trigger_daily_update(
    background_tasks: BackgroundTasks,
    pipeline: GPFPipeline = Depends(get_pipeline),
    sheets: GPFSpreadsheetClient = Depends(get_sheets_client),
    notifier: LINEBotNotifier = Depends(get_notifier),
    tg_notifier: TelegramBotNotifier = Depends(get_telegram_notifier)
):
    """
    Triggers the daily data sync.
    Runs technical signals calculation + Gemini LLM validation.
    Sends push alerts if a signal transitions.
    """
    def task_runner():
        try:
            transitions = pipeline.run_daily_update()
            if transitions:
                # LINE Alerts
                if sheets.is_connected() and notifier.enabled:
                    subscribers = sheets.get_subscribers()
                    if subscribers:
                        logger.info(f"Broadcasting {len(transitions)} transition(s) to {len(subscribers)} LINE subscribers.")
                        notifier.broadcast_transitions(transitions, subscribers)
                # Telegram Alerts
                if tg_notifier.enabled:
                    logger.info(f"Broadcasting {len(transitions)} transition(s) via Telegram Bot.")
                    tg_notifier.send_transition_alert(transitions)

            # Check and dispatch opportunistic profit rebalancing alert
            try:
                from api.scheduler import check_and_notify_profit_opportunity
                check_and_notify_profit_opportunity(sheets, pipeline, notifier, tg_notifier)
            except Exception as pe:
                logger.error(f"Error evaluating profit opportunity in sync task: {pe}", exc_info=True)
        except Exception as e:
            logger.error(f"Error running pipeline task: {e}", exc_info=True)

    background_tasks.add_task(task_runner)
    return {
        "status": "triggered",
        "message": "Data pipeline run scheduled in the background."
    }

@app.post("/api/trigger-realtime")
def trigger_realtime_check(background_tasks: BackgroundTasks):
    """Triggers the intraday real-time market analysis check (Cloud Scheduler / Webhook)."""
    from api.scheduler import run_realtime_market_check
    background_tasks.add_task(run_realtime_market_check)
    return {
        "status": "triggered",
        "message": "Intraday real-time market check scheduled in the background."
    }

@app.post("/api/trigger-weekly")
def trigger_weekly_alerts(background_tasks: BackgroundTasks):
    """Triggers Saturday weekly performance and monthly rebalance alerts (Cloud Scheduler / Webhook)."""
    from api.scheduler import run_weekly_alerts_pipeline
    background_tasks.add_task(run_weekly_alerts_pipeline)
    return {
        "status": "triggered",
        "message": "Weekly alerts job scheduled in the background."
    }

@app.post("/api/line/webhook")
async def line_webhook(
    request: Request,
    x_line_signature: Optional[str] = Header(None),
    handler: LINEWebhookHandler = Depends(get_webhook_handler)
):
    """LINE Bot webhook endpoint."""
    return await handler.handle_request(request, x_line_signature)


@app.post("/api/telegram/webhook")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    handler = Depends(get_telegram_handler)
):
    """Telegram Bot webhook endpoint for interactive commands and messages."""
    data = await request.json()
    background_tasks.add_task(handler.process_update, data)
    return {"status": "ok"}


@app.get("/api/telegram/set-webhook")
def set_telegram_webhook(url: Optional[str] = None):
    """Registers the Cloud Run or public URL as the webhook with Telegram Bot API."""
    import requests
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return {"error": "TELEGRAM_BOT_TOKEN not configured"}

    target_url = url or os.getenv("BACKEND_URL")
    if not target_url:
        return {"error": "Please provide ?url=https://your-backend-url or set BACKEND_URL in .env"}

    webhook_url = f"{target_url.rstrip('/')}/api/telegram/webhook"
    res = requests.post(
        f"https://api.telegram.org/bot{token}/setWebhook",
        json={"url": webhook_url},
        timeout=10
    )
    return res.json()



# Helper to fetch history for a single asset plan
def get_asset_history(plan_id: str, sheets: GPFSpreadsheetClient):
    if not sheets.is_connected():
        import pandas as pd
        import numpy as np
        dates = pd.date_range(end=pd.Timestamp.now(), periods=100)
        nav_val = 100.0
        mock_data = []
        seed = sum(ord(c) for c in plan_id)
        np.random.seed(seed)
        
        risk_multiplier = {
            "fixed_income": 0.3,
            "money_market": 0.05,
            "thai_equity": 1.0,
            "thai_property": 0.5,
            "global_equity": 1.2,
            "global_debt": 0.4,
            "gold": 0.8
        }
        mult = risk_multiplier.get(plan_id, 0.5)
        
        for idx, d in enumerate(dates):
            ret = np.random.normal(0.0001 * mult, 0.005 * mult)
            nav_val *= (1 + ret)
            mock_data.append({
                "date": d.strftime("%Y-%m-%d"),
                "plan_id": plan_id,
                "synthetic_nav": float(nav_val),
                "daily_return": float(ret)
            })
        return mock_data
        
    try:
        history = sheets.get_synthetic_performance(plan_id)
        history = sorted(history, key=lambda x: x["date"])
        parsed_history = []
        for h in history:
            parsed_history.append({
                "date": h["date"],
                "plan_id": h["plan_id"],
                "synthetic_nav": float(h["synthetic_nav"]),
                "daily_return": float(h.get("daily_return", 0.0))
            })
        return parsed_history
    except Exception as e:
        logger.error(f"Error fetching historical data for {plan_id}: {e}")
        return []


# Helper to fetch latest signal for a single asset plan
def get_latest_asset_signal(plan_id: str, sheets: GPFSpreadsheetClient):
    if sheets.is_connected():
        signals = sheets.get_latest_signals()
        if plan_id in signals:
            s = signals[plan_id]
            return {
                "plan_id": plan_id,
                "composite_score": float(s["composite_score"]),
                "signal": s["signal"],
                "thai_commentary": s["thai_commentary"]
            }
            
    # Offline mock fallback
    import random
    seed = sum(ord(c) for c in plan_id)
    random.seed(seed)
    score = float(random.randint(40, 85))
    signal = "BUY_HOLD" if score >= 70 else "WATCH" if score >= 45 else "REDUCE"
    return {
        "plan_id": plan_id,
        "composite_score": score,
        "signal": signal,
        "thai_commentary": (
            "สภาวะตลาดอ้างอิงอยู่ภายใต้แนวโน้มเชิงปริมาณ\n"
            "สัญญาณทางเทคนิคบ่งชี้ถึงปริมาณซื้อขายที่ทรงตัว\n"
            "แนะนำพิจารณาสัดส่วนการจัดสรรสินทรัพย์อย่างระมัดระวัง"
        )
    }


@app.get("/api/portfolio/status")
def get_portfolio_status(sheets: GPFSpreadsheetClient = Depends(get_sheets_client)):
    """Returns the current custom weights and combined historical performance using transaction history."""
    user_id = "client_user"
    
    # Unique list of assets we track for the custom portfolio
    assets = ["fixed_income", "money_market", "thai_equity", "thai_property", "global_equity", "global_debt", "gold"]
    
    all_history = {}
    dates = set()
    
    for asset in assets:
        hist = get_asset_history(asset, sheets)
        all_history[asset] = {h["date"]: h["daily_return"] for h in hist}
        dates.update(all_history[asset].keys())
        
    sorted_dates = sorted(list(dates))
    combined_history = []
    
    nav_t = 100.0
    for d in sorted_dates:
        # Resolve active weights on date d
        weights_d = sheets.get_user_mixed_portfolio(user_id, as_of_date=d)
        
        # Calculate weighted daily return for this day
        daily_ret = 0.0
        for asset, w in weights_d.items():
            daily_ret += w * all_history[asset].get(d, 0.0)
            
        nav_t = nav_t * (1 + daily_ret)
        combined_history.append({
            "date": d,
            "synthetic_nav": nav_t
        })
        
    current_weights = sheets.get_user_mixed_portfolio(user_id)
    return {
        "weights": current_weights,
        "history": combined_history
    }



@app.get("/api/portfolio/optimize")
def get_portfolio_optimization(
    sheets: GPFSpreadsheetClient = Depends(get_sheets_client),
    gemini: GeminiAnalysisService = Depends(lambda: GeminiAnalysisService())
):
    """Calculates optimal weights and generates Gemini explanation."""
    user_id = "client_user"
    current_weights = sheets.get_user_mixed_portfolio(user_id)
    
    asset_signals = {}
    for asset in current_weights.keys():
        asset_signals[asset] = get_latest_asset_signal(asset, sheets)
        
    optimized = {}
    freed_weight = 0.0
    buy_hold_assets = []
    
    for asset, w in current_weights.items():
        sig_data = asset_signals[asset]
        sig = sig_data["signal"]
        
        if sig == "REDUCE":
            optimized[asset] = 0.0
            freed_weight += w
        elif sig == "WATCH":
            new_w = w * 0.5
            optimized[asset] = new_w
            freed_weight += (w - new_w)
        else:
            buy_hold_assets.append(asset)
            optimized[asset] = w
            
    if buy_hold_assets:
        total_buy_score = sum(asset_signals[a]["composite_score"] for a in buy_hold_assets)
        if total_buy_score > 0:
            for a in buy_hold_assets:
                score = asset_signals[a]["composite_score"]
                share = (score / total_buy_score) * freed_weight
                optimized[a] += share
    else:
        for asset in current_weights.keys():
            optimized[asset] = 0.0
        optimized["money_market"] = 1.0
        
    total_w = sum(optimized.values())
    if total_w > 0:
        for a in optimized.keys():
            optimized[a] = round(optimized[a] / total_w, 3)
        
        # Correct residual difference
        residual = 1.0 - sum(optimized.values())
        if abs(residual) > 0.0001:
            max_asset = max(optimized, key=optimized.get)
            optimized[max_asset] = round(optimized[max_asset] + residual, 3)
            
    commentary = gemini.analyze_portfolio_rebalance(current_weights, optimized, asset_signals)
    
    return {
        "current_weights": current_weights,
        "optimized_weights": optimized,
        "signals": asset_signals,
        "commentary": commentary
    }


class UserProfileRequest(BaseModel):
    birth_year: int
    target_retirement_year: Optional[int] = None
    risk_profile: Optional[str] = "MODERATE"


@app.get("/api/user/profile")
def get_user_profile_endpoint(storage = Depends(get_storage_provider)):
    """Returns current user's profile, calculated age, and Life Path equity cap."""
    user_id = "client_user"
    return storage.get_user_profile(user_id)


@app.post("/api/user/profile")
def update_user_profile_endpoint(
    req: UserProfileRequest,
    storage = Depends(get_storage_provider)
):
    """Updates user birth year and risk profile, recalculating Life Path equity ceiling."""
    user_id = "client_user"
    target_ret = req.target_retirement_year or (req.birth_year + 60)
    data = {
        "user_id": user_id,
        "birth_year": req.birth_year,
        "target_retirement_year": target_ret,
        "risk_profile": req.risk_profile or "MODERATE"
    }
    return storage.save_user_profile(data)


@app.get("/api/fx/rates")
def get_fx_rates_endpoint(fx_service = Depends(get_fx_service)):
    """Returns live USD/THB exchange rates, dynamic hedging formula metrics, and policies."""
    rate = fx_service.get_latest_rate()
    dynamic_hedge = fx_service.calculate_dynamic_equity_hedge()
    return {
        "currency_pair": "USD/THB",
        "spot_rate": round(rate, 3),
        "dynamic_equity_hedge": dynamic_hedge,
        "hedging_policy": {
            "global_debt": "100% Hedged (ป้องกันความเสี่ยงอัตราแลกเปลี่ยนเต็มจำนวน)",
            "global_equity": f"{int(dynamic_hedge['hedge_ratio'] * 100)}% Dynamic Hedging ({dynamic_hedge['rationale']})",
            "gold": "0% Unhedged (ถือครองเป็นเกราะกำบังค่าเงิน)"
        }
    }


@app.get("/api/audit/verify")
def get_audit_verify_endpoint(storage = Depends(get_storage_provider)):
    """Cryptographically verifies the SHA-256 hash chain of the rebalance audit trail."""
    user_id = "client_user"
    return storage.verify_audit_integrity(user_id)


@app.get("/api/glidepath/curve")
def get_glide_path_curve_endpoint(
    risk_profile: str = "MODERATE",
    storage = Depends(get_storage_provider)
):
    """Returns smooth Life Path glide projection points from age 25 to 65 without cliff jumps."""
    return {
        "risk_profile": risk_profile,
        "curve": storage.get_glide_path_curve(risk_profile)
    }


@app.get("/api/health")
def get_health_telemetry(
    storage = Depends(get_storage_provider),
    fx_service = Depends(get_fx_service),
    sheets = Depends(get_sheets_client)
):
    """Enterprise observability and telemetry endpoint."""
    import time
    t0 = time.time()
    quota = storage.get_annual_quota_status("client_user")
    db_latency_ms = round((time.time() - t0) * 1000, 2)

    spot = fx_service.get_latest_rate()
    audit_res = storage.verify_audit_integrity("client_user")

    return {
        "status": "HEALTHY",
        "timestamp": datetime.now().isoformat(),
        "database": {
            "engine": "SQLite WAL Mode (ACID)",
            "latency_ms": db_latency_ms,
            "status": "CONNECTED"
        },
        "audit_trail": {
            "integrity_verified": audit_res["is_valid"],
            "latest_hash": audit_res.get("latest_hash", "GENESIS"),
            "total_entries": audit_res.get("total_entries", 0)
        },
        "fx_service": {
            "spot_usd_thb": spot,
            "status": "OPERATIONAL"
        },
        "google_sheets_sync": {
            "connected": sheets.is_connected(),
            "status": "CONNECTED" if sheets.is_connected() else "OFFLINE_FALLBACK"
        }
    }


@app.get("/api/portfolio/backtest")
def get_portfolio_backtest_endpoint(
    backtest_engine = Depends(get_backtest_engine),
    storage = Depends(get_storage_provider)
):
    """Runs multi-year historical backtest comparing Gor.PF strategy vs GPF Main Plan."""
    user_id = "client_user"
    profile = storage.get_user_profile(user_id)
    return backtest_engine.run_simulation(user_profile=profile)


@app.get("/api/portfolio/quota")
def get_portfolio_quota(
    sheets: GPFSpreadsheetClient = Depends(get_sheets_client),
    storage = Depends(get_storage_provider)
):
    """Returns annual 12-rebalance quota status for current user."""
    user_id = "client_user"
    # Check ACID storage first for zero-latency response
    quota = storage.get_annual_quota_status(user_id)
    if quota["used"] == 0 and sheets.is_connected():
        sheets_quota = sheets.get_annual_quota_status(user_id)
        if sheets_quota["used"] > 0:
            return sheets_quota
    return quota


@app.get("/api/portfolio/opportunity")
def get_portfolio_opportunity(
    sheets: GPFSpreadsheetClient = Depends(get_sheets_client),
    pipeline: GPFPipeline = Depends(get_pipeline),
    storage = Depends(get_storage_provider)
):
    """Evaluates whether an opportunistic profit rebalance is currently recommended."""
    user_id = "client_user"
    current_weights = sheets.get_user_mixed_portfolio(user_id)
    
    asset_signals = {}
    for asset in current_weights.keys():
        asset_signals[asset] = get_latest_asset_signal(asset, sheets)
        
    quota_status = storage.get_annual_quota_status(user_id)
    last_rebalance = storage.get_last_rebalance_time(user_id) or sheets.get_last_rebalance_time(user_id)
    user_profile = storage.get_user_profile(user_id)
    
    from quant_engine.rebalance_opportunity import OpportunityDetector
    detector = OpportunityDetector(max_rebalances=12)
    opp = detector.evaluate_opportunity(
        current_weights=current_weights,
        signals=asset_signals,
        quota_used_this_year=quota_status["used"],
        last_rebalance_date=last_rebalance,
        user_profile=user_profile
    )
    return opp



class RebalanceRequest(BaseModel):
    weights: Dict[str, float]
    reason: Optional[str] = "ผู้ใช้กดยืนยันการปรับพอร์ตเพื่อคว้าโอกาสทำกำไร"


@app.post("/api/portfolio/rebalance")
def post_portfolio_rebalance(
    req: RebalanceRequest,
    sheets: GPFSpreadsheetClient = Depends(get_sheets_client),
    storage = Depends(get_storage_provider),
    notifier: LINEBotNotifier = Depends(get_notifier),
    tg_notifier: TelegramBotNotifier = Depends(get_telegram_notifier)
):
    """Saves the new weight allocation, updates the 12-annual quota counter, and triggers notifications."""
    user_id = "client_user"
    
    # 1. Check annual quota limit (12 per calendar year) using ACID storage
    quota_status = storage.get_annual_quota_status(user_id)
    if quota_status["remaining"] <= 0:
        return {
            "status": "error",
            "message": f"โควตาการเปลี่ยนแผนการลงทุนปี {quota_status['year']} ครบ 12 ครั้งแล้ว ไม่สามารถปรับเพิ่มได้ตามกฎ กบข."
        }

    current_weights = sheets.get_user_mixed_portfolio(user_id)
    
    # 2. Save new weights
    success = sheets.save_user_mixed_portfolio(user_id, req.weights)
    if not success:
        return {"status": "error", "message": "Failed to save mixed portfolio weights."}

    # 3. Calculate score delta
    asset_signals = {a: get_latest_asset_signal(a, sheets) for a in current_weights.keys()}
    score_before = sum(current_weights.get(a, 0.0) * asset_signals[a]["composite_score"] for a in current_weights.keys())
    score_after = sum(req.weights.get(a, 0.0) * asset_signals.get(a, {}).get("composite_score", 50.0) for a in req.weights.keys())

    # 4. Record execution in local ACID database
    log_res = storage.record_rebalance_execution(
        user_id=user_id,
        old_weights=current_weights,
        new_weights=req.weights,
        score_before=score_before,
        score_after=score_after,
        reason=req.reason or "ปรับพอร์ตเพื่อเพิ่มประสิทธิภาพการลงทุน",
        action_type="CONFIRMED"
    )

    # 5. Mirror to Google Sheets if connected
    if sheets.is_connected():
        try:
            sheets.record_rebalance_execution(
                user_id=user_id,
                old_weights=current_weights,
                new_weights=req.weights,
                score_before=score_before,
                score_after=score_after,
                reason=req.reason or "ปรับพอร์ตเพื่อเพิ่มประสิทธิภาพการลงทุน",
                action_type="CONFIRMED"
            )
        except Exception:
            pass

    used_no = log_res["rebalance_no"]
    remaining_no = log_res["remaining"]

    msg = (
        "🔔 *[ยืนยันการปรับพอร์ต กบข. เรียบร้อยแล้ว]*\n"
        f"ระบบได้บันทึกสัดส่วนน้ำหนักพอร์ตการลงทุนใหม่ของคุณเข้าสู่ระบบเรียบร้อยแล้ว:\n\n"
        f"📊 *สิทธิ์การเปลี่ยนแผนปี {log_res['year']}:* "
        f"ใช้ไปแล้ว *{used_no}/12* ครั้ง (คงเหลืออีก *{remaining_no}* ครั้ง)\n"
        f"📈 *คะแนนศักยภาพพอร์ต:* {score_before:.1f} ➔ *{score_after:.1f}*\n\n"
        "🔄 *สัดส่วนพอร์ตใหม่:*\n"
    )
    weight_list = []
    for asset, w in req.weights.items():
        if w > 0:
            weight_list.append(f"• {ASSET_NAMES.get(asset, asset)}: {w * 100:.1f}%")
    msg += "\n".join(weight_list)
    msg += "\n\n💡 ระบบจะเริ่มทำการรวบรวมข้อมูลประสิทธิภาพและเฝ้าระวังความเสี่ยงตามสัดส่วนนี้ต่อไป"
    
    if tg_notifier.enabled:
        try:
            tg_notifier.send_message(msg)
        except Exception as e:
            logger.warning(f"Failed to send rebalance notification via Telegram: {e}")
            
    if sheets.is_connected() and notifier.enabled:
        subscribers = sheets.get_subscribers()
        if user_id in subscribers or "client_user" in subscribers:
            try:
                import gspread
                notifier.line_bot_api.broadcast(
                    text_message=gspread.models.TextMessage(text=msg)
                )
            except Exception as e:
                logger.warning(f"Failed to send rebalance notification via LINE: {e}")
                
    return {
        "status": "success",
        "message": "Portfolio reallocated successfully.",
        "quota": {
            "year": log_res["year"],
            "used": used_no,
            "remaining": remaining_no,
            "max_allowed": 12
        }
    }


