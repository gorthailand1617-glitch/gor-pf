import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from data_pipeline.pipeline import GPFPipeline
from data_pipeline.gspread_client import GPFSpreadsheetClient
from line_bot.notifier import LINEBotNotifier
from telegram_bot.notifier import TelegramBotNotifier
from quant_engine.rebalance_opportunity import OpportunityDetector

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


# Date helpers for weekly/monthly schedules
def is_last_saturday(dt: datetime) -> bool:
    if dt.weekday() != 5:  # Saturday is 5
        return False
    next_week = dt + timedelta(days=7)
    return next_week.month != dt.month


def is_second_or_fourth_saturday(dt: datetime) -> bool:
    if dt.weekday() != 5:
        return False
    d = dt.day
    return (8 <= d <= 14) or (22 <= d <= 28)


# Helper to fetch history for a single asset plan (same as api/main.py)
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


# Helper to calculate ROI of the user's custom portfolio over the last N days
def calculate_portfolio_roi(sheets: GPFSpreadsheetClient, days: int = 14) -> Dict[str, Any]:
    user_id = "client_user"
    assets = ["fixed_income", "money_market", "thai_equity", "thai_property", "global_equity", "global_debt", "gold"]
    
    all_history = {}
    dates = set()
    for asset in assets:
        hist = get_asset_history(asset, sheets)
        all_history[asset] = {h["date"]: h["daily_return"] for h in hist}
        dates.update(all_history[asset].keys())
        
    sorted_dates = sorted(list(dates))
    if len(sorted_dates) < 2:
        return {"roi": 0.0, "nav_today": 100.0, "nav_prev": 100.0, "date_today": "", "date_prev": ""}
        
    nav_t = 100.0
    nav_history = []
    for d in sorted_dates:
        weights_d = sheets.get_user_mixed_portfolio(user_id, as_of_date=d)
        daily_ret = 0.0
        for asset, w in weights_d.items():
            daily_ret += w * all_history[asset].get(d, 0.0)
        nav_t = nav_t * (1 + daily_ret)
        nav_history.append({"date": d, "nav": nav_t})
        
    latest = nav_history[-1]
    nav_today = latest["nav"]
    
    prev_idx = max(0, len(nav_history) - 1 - days)
    prev = nav_history[prev_idx]
    nav_prev = prev["nav"]
    
    roi = (nav_today / nav_prev - 1) * 100
    return {
        "roi": roi,
        "nav_today": nav_today,
        "nav_prev": nav_prev,
        "date_today": latest["date"],
        "date_prev": prev["date"]
    }


def check_and_notify_profit_opportunity(
    sheets: GPFSpreadsheetClient,
    pipeline: GPFPipeline,
    notifier: LINEBotNotifier,
    tg_notifier: TelegramBotNotifier
) -> Optional[Dict[str, Any]]:
    """
    Evaluates market conditions to detect profit opportunities while respecting the 12 annual rebalances quota.
    Dispatches alerts via Telegram and LINE when an actionable opportunity is identified.
    """
    logger.info("Evaluating opportunistic profit rebalancing conditions...")
    try:
        user_id = "client_user"
        current_weights = sheets.get_user_mixed_portfolio(user_id)
        
        # Build asset signals map
        latest_signals = {}
        if pipeline.latest_results:
            latest_signals = {r["plan_id"]: r for r in pipeline.latest_results}
        elif sheets.is_connected():
            latest_signals = sheets.get_latest_signals()
            
        if not latest_signals:
            pipeline.run_daily_update(persist=False)
            latest_signals = {r["plan_id"]: r for r in pipeline.latest_results}
            
        quota_status = sheets.get_annual_quota_status(user_id)
        last_rebalance = sheets.get_last_rebalance_time(user_id)
        
        detector = OpportunityDetector(max_rebalances=12)
        opp = detector.evaluate_opportunity(
            current_weights=current_weights,
            signals=latest_signals,
            quota_used_this_year=quota_status["used"],
            last_rebalance_date=last_rebalance
        )
        
        if opp["is_opportunity"]:
            dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:3000")
            msg = detector.format_alert_message(opp, dashboard_url=dashboard_url)
            logger.info(f"Profit opportunity detected! ({opp['opportunity_type']}): {opp['reason']}")
            
            if tg_notifier.enabled:
                tg_notifier.send_message(msg)
                
            if sheets.is_connected() and notifier.enabled:
                subscribers = sheets.get_subscribers()
                if user_id in subscribers or "client_user" in subscribers:
                    try:
                        import gspread
                        notifier.line_bot_api.broadcast(
                            text_message=gspread.models.TextMessage(text=msg)
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send opportunity alert via LINE: {e}")
            return opp
        else:
            logger.info(f"No profit opportunity trigger at this time: {opp['reason']}")
            return None
    except Exception as e:
        logger.error(f"Error checking profit opportunity: {e}", exc_info=True)
        return None


def run_scheduled_pipeline():
    """Triggered by APScheduler at 18:30 ICT on weekdays."""
    logger.info("Executing scheduled daily pipeline update job...")
    try:
        sheets = GPFSpreadsheetClient()
        pipeline = GPFPipeline(sheets_client=sheets)
        notifier = LINEBotNotifier()
        tg_notifier = TelegramBotNotifier()
        
        transitions = pipeline.run_daily_update()
        
        # 1. Always broadcast Daily Market Summary at 18:30 ICT
        if pipeline.latest_results:
            logger.info("Broadcasting scheduled daily market summary...")
            if tg_notifier.enabled:
                tg_notifier.send_daily_summary(pipeline.latest_results)

        # 2. Broadcast transition alerts if any asset plan flipped its signal
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

        # 3. Evaluate profit opportunity and quota
        check_and_notify_profit_opportunity(sheets, pipeline, notifier, tg_notifier)
    except Exception as e:
        logger.error(f"Error running scheduled pipeline job: {e}", exc_info=True)


def run_realtime_market_check():
    """Triggered by APScheduler hourly on weekdays from 10:00 to 17:00 ICT."""
    logger.info("Executing real-time market analysis check...")
    try:
        sheets = GPFSpreadsheetClient()
        pipeline = GPFPipeline(sheets_client=sheets)
        notifier = LINEBotNotifier()
        tg_notifier = TelegramBotNotifier()
        
        # Run pipeline in memory (persist=False). Alerts standard transitions immediately.
        transitions = pipeline.run_daily_update(persist=False)
        
        if transitions:
            logger.info(f"Real-time transition detected! Broadcasting {len(transitions)} transition(s).")
            if sheets.is_connected() and notifier.enabled:
                subscribers = sheets.get_subscribers()
                if subscribers:
                    notifier.broadcast_transitions(transitions, subscribers)
            if tg_notifier.enabled:
                tg_notifier.send_transition_alert(transitions)

        # Check for urgent intraday profit opportunity or severe breakdown
        check_and_notify_profit_opportunity(sheets, pipeline, notifier, tg_notifier)
    except Exception as e:
        logger.error(f"Error running real-time market check: {e}", exc_info=True)


def run_weekly_alerts_pipeline():
    """Triggered by APScheduler at 10:00 AM ICT on Saturdays."""
    logger.info("Executing scheduled Saturday alerts check...")
    try:
        sheets = GPFSpreadsheetClient()
        notifier = LINEBotNotifier()
        tg_notifier = TelegramBotNotifier()
        
        now = datetime.now()
        user_id = "client_user"
        
        # 1. Last Saturday of Month -> Rebalancing recommendation alert
        if is_last_saturday(now):
            logger.info("Today is the last Saturday of the month. Triggering rebalancing alerts...")
            pipeline = GPFPipeline(sheets_client=sheets)
            # Run daily update in-memory to get latest signals
            pipeline.run_daily_update(persist=False)
            latest_signals = {r["plan_id"]: r for r in pipeline.latest_results}
            
            current_weights = sheets.get_user_mixed_portfolio(user_id)
            
            optimized = {}
            freed_weight = 0.0
            buy_hold_assets = []
            for asset, w in current_weights.items():
                sig_data = latest_signals.get(asset, {"signal": "WATCH", "composite_score": 50.0})
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
                total_buy_score = sum(latest_signals.get(a, {}).get("composite_score", 50.0) for a in buy_hold_assets)
                if total_buy_score > 0:
                    for a in buy_hold_assets:
                        score = latest_signals.get(a, {}).get("composite_score", 50.0)
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
                    
            adjustments = []
            for asset, curr_w in current_weights.items():
                opt_w = optimized.get(asset, 0.0)
                diff = opt_w - curr_w
                if abs(diff) > 0.001:
                    diff_pct = diff * 100
                    asset_name = ASSET_NAMES.get(asset, asset)
                    if diff > 0:
                        adjustments.append(f"📈 ปรับเพิ่ม {asset_name}: +{diff_pct:.1f}%")
                    else:
                        adjustments.append(f"📉 ปรับลด {asset_name}: {diff_pct:.1f}%")
                        
            if adjustments:
                alert_msg = (
                    "🔔 *[คำแนะนำปรับสัดส่วนพอร์ตผสมเองประจำเดือน]*\n"
                    "ครบกำหนดตรวจสุขภาพพอร์ตประจำเดือนนี้ AI แนะนำให้ทำการปรับสัดส่วนการลงทุนดังนี้ เพื่อเพิ่มโอกาสทำกำไรสูงสุด:\n\n"
                    + "\n".join(adjustments) + "\n\n"
                    "🔗 [กดยืนยันปรับสัดส่วนที่ Dashboard](http://localhost:3000)"
                )
                if tg_notifier.enabled:
                    tg_notifier.send_message(alert_msg)
                if sheets.is_connected() and notifier.enabled:
                    subscribers = sheets.get_subscribers()
                    if user_id in subscribers or "client_user" in subscribers:
                        try:
                            import gspread
                            notifier.line_bot_api.broadcast(
                                text_message=gspread.models.TextMessage(text=alert_msg)
                            )
                        except Exception as e:
                            logger.warning(f"Failed to send monthly rebalance alert: {e}")
                            
        # 2. 2nd or 4th Saturday of Month -> Profit/Loss Performance Alert
        if is_second_or_fourth_saturday(now):
            logger.info("Today is the 2nd or 4th Saturday of the month. Triggering profit/loss performance alerts...")
            perf = calculate_portfolio_roi(sheets, days=14)
            roi = perf["roi"]
            nav_today = perf["nav_today"]
            nav_prev = perf["nav_prev"]
            
            symbol = "🟢" if roi >= 0 else "🔴"
            sign = "+" if roi >= 0 else ""
            
            # Retrieve simulation investment balance
            investment = 100000.0
            if sheets.is_connected():
                try:
                    records = sheets.sh.worksheet("User_Mixed_Portfolio").get_all_records()
                    user_recs = [r for r in records if r["user_id"] == user_id]
                    if user_recs:
                        latest_d = max(r["date"] for r in user_recs)
                        investment = sum(float(r["balance"]) for r in user_recs if r["date"] == latest_d)
                except Exception:
                    pass
                    
            profit_loss_val = investment * (roi / 100)
            
            alert_msg = (
                f"📊 *[รายงานผลกำไร-ขาดทุนพอร์ตผสมเองประจำสัปดาห์]*\n"
                f"สรุปความเคลื่อนไหวพอร์ตการลงทุน กบข. ของคุณ:\n\n"
                f"• ช่วงเวลาประเมิน: {perf['date_prev']} ถึง {perf['date_today']}\n"
                f"• มูลค่าพอร์ต กบข. จำลอง: {investment:,.0f} THB\n"
                f"• NAV ปัจจุบัน: {nav_today:.2f} (เทียบกับเดิม {nav_prev:.2f})\n"
                f"• ผลตอบแทนรอบ 2 สัปดาห์: {symbol} *{sign}{roi:.2f}%*\n"
                f"• กำไร/ขาดทุนโดยประมาณ: *{sign}{profit_loss_val:+,.2f} THB*\n\n"
                f"🔗 [เข้าชมกราฟประสิทธิภาพที่ Dashboard](http://localhost:3000)"
            )
            
            if tg_notifier.enabled:
                tg_notifier.send_message(alert_msg)
            if sheets.is_connected() and notifier.enabled:
                subscribers = sheets.get_subscribers()
                if user_id in subscribers or "client_user" in subscribers:
                    try:
                        import gspread
                        notifier.line_bot_api.broadcast(
                            text_message=gspread.models.TextMessage(text=alert_msg)
                        )
                    except Exception as e:
                        logger.warning(f"Failed to send performance alert: {e}")
                        
    except Exception as e:
        logger.error(f"Error running weekly Saturday alerts: {e}", exc_info=True)


def start_scheduler():
    """Initializes and starts the weekday cron scheduler."""
    scheduler = BackgroundScheduler()
    
    # 1. Run daily persist sync at 18:30 ICT (Asia/Bangkok timezone) on weekdays Monday-Friday
    daily_trigger = CronTrigger(
        day_of_week="mon-fri",
        hour=18,
        minute=30,
        timezone="Asia/Bangkok"
    )
    
    scheduler.add_job(
        run_scheduled_pipeline,
        trigger=daily_trigger,
        name="daily_market_sync_job",
        replace_existing=True
    )
    
    # 2. Run hourly real-time analysis at minutes 0 from 10:00 to 17:00 ICT on weekdays Monday-Friday
    realtime_trigger = CronTrigger(
        day_of_week="mon-fri",
        hour="10-17",
        minute="0",
        timezone="Asia/Bangkok"
    )
    
    scheduler.add_job(
        run_realtime_market_check,
        trigger=realtime_trigger,
        name="realtime_market_check_job",
        replace_existing=True
    )
    
    # 3. Run weekly alerts check on Saturdays at 10:00 AM ICT
    weekly_trigger = CronTrigger(
        day_of_week="sat",
        hour=10,
        minute=0,
        timezone="Asia/Bangkok"
    )
    
    scheduler.add_job(
        run_weekly_alerts_pipeline,
        trigger=weekly_trigger,
        name="weekly_saturday_alerts_job",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("APScheduler initialized: Weekday daily sync, Weekday hourly real-time, & Saturday weekly alerts scheduled.")
    return scheduler
