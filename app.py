"""
GPF Smart Investor AI - Hugging Face Gradio Space Entrypoint
Runs 24/7 in the cloud:
- Starts APScheduler (Daily 18:30 ICT Market Briefing & Saturday Rebalance Alerts)
- Starts Telegram Bot Polling (@Gor_Gpf_bot)
- Provides an interactive Gradio Dashboard & AI Chat interface
"""
import os
os.environ["GRADIO_SSR"] = "False"
import sys
import threading
import time
import logging
from datetime import datetime
from dotenv import load_dotenv
import gradio as gr

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("HF_Space_App")

# Shared state for UI
app_state = {
    "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S ICT"),
    "scheduler_status": "Starting...",
    "telegram_status": "Starting...",
    "last_sync_time": "None",
    "last_sync_result": "No sync executed yet."
}

# 1. Background Service Initializer
_bg_started = False
def start_background_services():
    global _bg_started, app_state
    if _bg_started:
        return
    _bg_started = True
    
    # 1.1 Start APScheduler
    try:
        from api.scheduler import start_scheduler
        scheduler = start_scheduler()
        app_state["scheduler_status"] = "Active 🟢 (Daily 18:30 ICT & Sat 10:00 ICT)"
        logger.info("APScheduler started successfully in background.")
    except Exception as e:
        app_state["scheduler_status"] = f"Warning: {e}"
        logger.warning(f"Could not start APScheduler: {e}")

    # 1.2 Start Telegram Polling
    try:
        from telegram_bot.webhook import TelegramWebhookHandler, start_telegram_polling
        handler = TelegramWebhookHandler()
        if handler.bot_token:
            thread = start_telegram_polling(handler)
            app_state["telegram_status"] = "Online 🟢 (@Gor_Gpf_bot actively listening)"
            logger.info("Telegram Bot polling started successfully. Bot is ONLINE 🟢!")
        else:
            app_state["telegram_status"] = "Offline 🟡 (TELEGRAM_BOT_TOKEN not configured)"
            logger.warning("⚠️ TELEGRAM_BOT_TOKEN not found in environment/secrets! Please add it in Settings > Variables and secrets.")
    except Exception as e:
        app_state["telegram_status"] = f"Error: {e}"
        logger.warning(f"Could not start Telegram Bot: {e}")

# Start background services once when imported/launched
bg_thread = threading.Thread(target=start_background_services, daemon=True)
bg_thread.start()


# 2. Action Functions for UI Buttons
def trigger_market_sync():
    """Manual trigger for daily market sync & Telegram broadcast"""
    global app_state
    try:
        from data_pipeline.gspread_client import GPFSpreadsheetClient
        from data_pipeline.pipeline import GPFPipeline
        from telegram_bot.notifier import TelegramBotNotifier
        from api.scheduler import check_and_notify_profit_opportunity

        sheets = GPFSpreadsheetClient()
        tg_notifier = TelegramBotNotifier()
        pipeline = GPFPipeline(sheets_client=sheets)

        transitions = pipeline.run_daily_update(persist=sheets.is_connected())

        summary_text = "✅ Market Sync Completed Successfully!\n"
        if pipeline.latest_results:
            if tg_notifier.enabled:
                tg_notifier.send_daily_summary(pipeline.latest_results)
                summary_text += "📡 Daily Market Summary sent to Telegram.\n"

        if transitions:
            if tg_notifier.enabled:
                tg_notifier.send_transition_alert(transitions)
                summary_text += f"🔔 {len(transitions)} Transition alert(s) sent to Telegram.\n"

        app_state["last_sync_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S ICT")
        app_state["last_sync_result"] = summary_text
        return summary_text
    except Exception as e:
        err_msg = f"❌ Error running sync: {str(e)}"
        logger.error(err_msg)
        return err_msg

def trigger_rebalance_analysis():
    """Manual trigger for Saturday portfolio rebalance check"""
    try:
        from api.scheduler import run_weekly_alerts_pipeline
        run_weekly_alerts_pipeline()
        return "✅ Weekly Rebalance & Performance Analysis executed and sent to Telegram/LINE!"
    except Exception as e:
        err_msg = f"❌ Error during rebalance analysis: {str(e)}"
        logger.error(err_msg)
        return err_msg

def send_test_telegram():
    """Send a test message to verify Telegram bot connection"""
    try:
        from telegram_bot.notifier import TelegramBotNotifier
        notifier = TelegramBotNotifier()
        if not notifier.enabled:
            return "🟡 Telegram Bot is disabled. Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in environment."
        
        test_msg = (
            "🔔 <b>Gor.PF Cloud Notification Test</b>\n"
            f"📅 เวลา: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            "🟢 ระบบ Gor.PF บน Hugging Face Space ทำงานออนไลน์ 24/7 สมบูรณ์แบบ!"
        )
        ok = notifier.send_message(test_msg)
        if ok:
            return "✅ ข้อความทดสอบส่งเข้า Telegram สำเร็จเรียบร้อยแล้ว!"
        else:
            return "❌ ไม่สามารถส่งข้อความได้ กรุณาตรวจสอบ Chat ID"
    except Exception as e:
        return f"❌ ข้อผิดพลาด: {str(e)}"

def ask_gpf_ai(user_question, history):
    """Interactive AI Assistant using Gemini & GPF Context"""
    try:
        from llm_service.gemini_client import GeminiAnalysisService
        from data_pipeline.gspread_client import GPFSpreadsheetClient
        
        gemini = GeminiAnalysisService()
        sheets = GPFSpreadsheetClient()
        
        weights = sheets.get_current_weights() if sheets.is_connected() else {}
        signals = sheets.get_latest_signals() if sheets.is_connected() else {}
        quota = sheets.get_annual_quota_status() if sheets.is_connected() else {}
        
        # Convert history format if provided
        conv_history = []
        if history:
            for item in history:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    conv_history.append({"role": "user", "content": str(item[0])})
                    conv_history.append({"role": "model", "content": str(item[1])})
                elif isinstance(item, dict):
                    conv_history.append(item)

        response = gemini.ask_portfolio_advisor(
            user_question=user_question,
            current_weights=weights,
            signals=signals,
            quota_status=quota,
            conversation_history=conv_history
        )
        return response
    except Exception as e:
        return f"ขออภัย ไม่สามารถตอบคำถามได้ในขณะนี้: {str(e)}"

def get_system_status():
    """Return live status markdown"""
    return f"""
### 📊 สถานะระบบ Gor.PF Cloud Service (24/7)
- ⏰ **เวลาเริ่มระบบ:** `{app_state['start_time']}`
- ⚙️ **APScheduler (ตั้งเวลาอัตโนมัติ):** {app_state['scheduler_status']}
- 🤖 **Telegram Bot Service:** {app_state['telegram_status']}
- 🕒 **การรัน Market Sync ล่าสุด:** `{app_state['last_sync_time']}`
- 📄 **ผลการรันล่าสุด:** {app_state['last_sync_result']}
"""


# 3. Build Modern Gradio UI
with gr.Blocks(title="Gor.PF - GPF Smart Investor AI", theme=gr.themes.Soft()) as demo:
    gr.Markdown("""
    # 🏛️ GPF Smart Investor AI - Cloud Service (24/7)
    ### ระบบวิเคราะห์การลงทุน กบข. อัจฉริยะ & แจ้งเตือนอัตโนมัติ
    """)
    
    with gr.Tabs():
        with gr.TabItem("🖥️ Dashboard & ควบคุมระบบ"):
            status_box = gr.Markdown(value=get_system_status)
            refresh_btn = gr.Button("🔄 รีเฟรชสถานะ", size="sm")
            refresh_btn.click(fn=get_system_status, outputs=status_box)

            gr.Markdown("---")
            gr.Markdown("### ⚡ คำสั่งลัด (Manual Triggers)")
            with gr.Row():
                btn_sync = gr.Button("🚀 ดึงข้อมูลตลาด & ส่งสรุปทันที (Sync Now)", variant="primary")
                btn_rebalance = gr.Button("📈 ตรวจสอบการปรับพอร์ต (Rebalance Check)", variant="secondary")
                btn_test_tg = gr.Button("📡 ทดสอบส่งข้อความ Telegram", variant="secondary")
            
            output_box = gr.Textbox(label="📋 ผลลัพธ์การทำงาน", lines=4, interactive=False)
            
            btn_sync.click(fn=trigger_market_sync, outputs=output_box)
            btn_rebalance.click(fn=trigger_rebalance_analysis, outputs=output_box)
            btn_test_tg.click(fn=send_test_telegram, outputs=output_box)

        with gr.TabItem("💬 สนทนากับ AI กบข."):
            gr.Markdown("พิมพ์คำถามเกี่ยวกับแผน กบข., การจัดสรรพอร์ต, หรือสถานะตลาดหุ้นได้ทันที")
            gr.ChatInterface(
                fn=ask_gpf_ai,
                type="messages",
                examples=[
                    "ตอนนี้ฉันลงทุนอะไรเท่าไร",
                    "เดือนนี้ฉันต้องปรับแผนอะไร",
                    "แนะนำแผน กบข. สำหรับคนรับความเสี่ยงได้ปานกลาง",
                    "ตลาดหุ้นโลกช่วงนี้เป็นอย่างไร"
                ],
                cache_examples=False
            )

        with gr.TabItem("ℹ️ ข้อมูลระบบ & การตั้งค่า"):
            gr.Markdown("""
            ### 📌 ตารางการทำงานอัตโนมัติของระบบ (ICT Thailand Time):
            1. **จันทร์ - ศุกร์ เวลา 18:30 น.:** คำนวณสรุปตลาดประจำวัน ดึง NAV กบข. และส่งสรุปเข้า Telegram
            2. **จันทร์ - ศุกร์ (ทุกชั่วโมง 10:00 - 17:00 น.):** ตรวจสอบตลาดแบบเรียลไทม์
            3. **ทุกวันเสาร์ เวลา 10:00 น.:** วิเคราะห์ประสิทธิภาพรายสัปดาห์ และประเมินจุดปรับพอร์ต (Rebalance Alert)
            4. **ตลอด 24 ชั่วโมง:** Telegram Bot `@Gor_Gpf_bot` รับคำสั่งและตอบคำถามสมาชิกได้ตลอดเวลา
            """)

if __name__ == "__main__":
    start_background_services()
    launch_kwargs = {
        "server_name": "0.0.0.0",
        "server_port": 7860,
    }
    import inspect
    sig = inspect.signature(demo.launch)
    if "ssr" in sig.parameters:
        launch_kwargs["ssr"] = False
    if "ssr_mode" in sig.parameters:
        launch_kwargs["ssr_mode"] = False
    demo.launch(**launch_kwargs)
    
    # Keep process alive so background threads continue
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
