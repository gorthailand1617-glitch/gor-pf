import os
import logging
import requests
from datetime import datetime
from typing import Dict, Any, Optional

from data_pipeline.gspread_client import GPFSpreadsheetClient
from quant_engine.rebalance_opportunity import OpportunityDetector

logger = logging.getLogger(__name__)


class TelegramWebhookHandler:
    def __init__(self, sheets_client: Optional[GPFSpreadsheetClient] = None):
        self._sheets = sheets_client
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.allowed_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.bot_token)

    @property
    def sheets(self) -> GPFSpreadsheetClient:
        if self._sheets is None:
            self._sheets = GPFSpreadsheetClient()
        return self._sheets

    def send_reply(self, chat_id: str, text: str) -> bool:
        """Sends a text message back to the user via Telegram."""
        if not self.bot_token:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            res = requests.post(url, json=payload, timeout=10)
            return res.status_code == 200
        except Exception as e:
            logger.error(f"Error replying to Telegram chat {chat_id}: {e}")
            return False

    def process_update(self, update: Dict[str, Any]):
        """Processes an incoming Telegram update object."""
        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))
        text = message.get("text", "").strip()

        if not text or not chat_id:
            return

        logger.info(f"Received Telegram command from chat_id {chat_id}: '{text}'")

        # Command routing
        cmd = text.split()[0].lower()
        if "@" in cmd:
            cmd = cmd.split("@")[0]  # Remove bot username suffix if any e.g. /ping@Gor_Gpf_bot

        user_from = message.get("from", {})
        first_name = user_from.get("first_name", "")
        username = user_from.get("username", "")
        display_name = f"{first_name} (@{username})".strip() if username else first_name

        if cmd in ["/ping", "/check"]:
            self._handle_ping(chat_id)
        elif cmd in ["/daily", "/summary", "/briefing"]:
            self._handle_daily(chat_id)
        elif cmd in ["/status"]:
            self._handle_status(chat_id)
        elif cmd in ["/quota"]:
            self._handle_quota(chat_id)
        elif cmd in ["/opportunity"]:
            self._handle_opportunity(chat_id)
        elif cmd in ["/rebalance"]:
            self._handle_opportunity(chat_id)
        elif cmd in ["/sync"]:
            self._handle_sync(chat_id)
        elif cmd in ["/start", "/subscribe"]:
            self._handle_subscribe(chat_id, display_name)
        elif cmd in ["/help"]:
            self._handle_help(chat_id)
        else:
            # Fallback reply
            fallback = (
                "🤖 ขออภัย ระบบไม่รู้จักคำสั่งนี้\n\n"
                "💡 ท่านสามารถพิมพ์คำสั่งดังนี้:\n"
                "👉 `/daily` : สรุปสภาวะตลาด กบข. ประจำวันแบบละเอียด\n"
                "👉 `/status` : ดูสัญญาณตลาดและคะแนนทั้ง 7 แผน\n"
                "👉 `/opportunity` : เช็คโอกาสทำกำไรและคำแนะนำปรับพอร์ต\n"
                "👉 `/quota` : เช็คสิทธิ์เปลี่ยนแผน กบข. ปีนี้ (12 ครั้ง/ปี)\n"
                "👉 `/sync` : สั่งประมวลผลข้อมูลตลาดวันนี้ใหม่ทันที\n"
                "👉 `/ping` : เช็คสถานะการทำงานของระบบ"
            )
            self.send_reply(chat_id, fallback)

    def _handle_ping(self, chat_id: str):
        now_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        sheets_status = "🟢 เชื่อมต่อสำเร็จ" if self.sheets.is_connected() else "🟡 โหมดจำลองข้อมูล (Offline Sheets)"
        msg = (
            "🟢 *[สถานะระบบ Gor.PF: ทำงานออนไลน์ตามปกติ]*\n\n"
            f"• เวลาปัจจุบัน: `{now_str}`\n"
            f"• สถานะเซิร์ฟเวอร์: `Online & Active (24/7)`\n"
            f"• ฐานข้อมูล Google Sheets: {sheets_status}\n"
            f"• โควตา กบข. ปี {datetime.now().year}: สูงสุด 12 ครั้ง/ปี\n\n"
            "ระบบกำลังเฝ้าระวังสัญญาณตลาดและพร้อมส่งการแจ้งเตือนทันทีเมื่อมีโอกาสทำกำไรครับ 🚀"
        )
        self.send_reply(chat_id, msg)

    def _handle_daily(self, chat_id: str):
        self.send_reply(chat_id, "⏳ กำลังประมวลผลสรุปสภาวะตลาด กบข. ประจำวัน กรุณารอสักครู่...")
        try:
            from data_pipeline.pipeline import GPFPipeline
            pipeline = GPFPipeline(sheets_client=self.sheets)
            pipeline.run_daily_update(persist=False)
            results = pipeline.latest_results
            if results:
                from telegram_bot.notifier import TelegramBotNotifier
                notifier = TelegramBotNotifier(bot_token=self.bot_token, chat_id=chat_id)
                notifier.send_daily_summary(results)
            else:
                self.send_reply(chat_id, "⚠️ ไม่สามารถประมวลผลข้อมูลตลาดได้ในขณะนี้")
        except Exception as e:
            logger.error(f"Error handling /daily command: {e}")
            self.send_reply(chat_id, f"⚠️ เกิดข้อผิดพลาดในการประมวลผลสรุปตลาด: {e}")

    def _handle_status(self, chat_id: str):
        signals = self.sheets.get_latest_signals()
        if not signals:
            try:
                from data_pipeline.pipeline import GPFPipeline
                pipeline = GPFPipeline(sheets_client=self.sheets)
                pipeline.run_daily_update(persist=False)
                signals = {r["plan_id"]: r for r in pipeline.latest_results}
            except Exception as e:
                logger.error(f"Error computing signals fallback: {e}")

        if not signals:
            self.send_reply(chat_id, "⚠️ ยังไม่มีข้อมูลสัญญาณในระบบ กรุณารอระบบรันตามรอบเวลา หรือพิมพ์ `/sync` เพื่อดึงข้อมูลใหม่")
            return

        lines = ["📊 *[สรุปสัญญาณแผนการลงทุน กบข. ล่าสุด]*\n"]
        emojis = {"BUY_HOLD": "🟢", "WATCH": "🟡", "REDUCE": "🔴"}
        
        plan_names = {
            "main": "Plan หลัก",
            "thai_equity": "Plan หุ้นไทย",
            "global_equity": "Plan หุ้นต่างประเทศ",
            "thai_property": "Plan อสังหาริมทรัพย์ไทย",
            "fixed_income": "แผนตราสารหนี้",
            "money_market": "แผนเงินฝาก/ตลาดเงิน",
            "global_debt": "แผนตราสารหนี้ต่างประเทศ",
            "gold": "แผนทองคำ"
        }

        for plan_id, s in signals.items():
            sig = s.get("signal", "WATCH")
            score = float(s.get("composite_score", 50.0))
            name = plan_names.get(plan_id, s.get("plan_name", plan_id))
            emoji = emojis.get(sig, "⚪")
            lines.append(f"• {name}: {emoji} *{sig}* ({score:.1f}/100)")

        dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:3000")
        lines.append(f"\n🔗 [เปิดเว็บ Dashboard]({dashboard_url})")
        self.send_reply(chat_id, "\n".join(lines))

    def _handle_quota(self, chat_id: str):
        user_id = "client_user"
        quota = self.sheets.get_annual_quota_status(user_id)
        
        # Build progress visual
        used = quota["used"]
        remaining = quota["remaining"]
        max_allowed = quota["max_allowed"]
        
        blocks = "🟩" * used + "⬜" * remaining

        msg = (
            f"📊 *[สิทธิ์การเปลี่ยนแผนการลงทุน กบข. ประจำปี {quota['year']}]*\n\n"
            f"• สถานะโควตา: *ใช้ไปแล้ว {used} / {max_allowed} ครั้ง*\n"
            f"• สิทธิ์คงเหลือ: *{remaining} ครั้ง*\n"
            f"• แถบสิทธิ์: {blocks}\n"
            f"• ปรับล่าสุด: `{quota['last_rebalance'] or 'ยังไม่มีประวัติการปรับในปีนี้'}`\n\n"
            f"💡 ตามระเบียบ กบข. สมาชิกสามารถเปลี่ยนแผนได้สูงสุด 12 ครั้งต่อปีปฏิทิน เพื่อเปิดโอกาสให้ปรับตามสภาวะเศรษฐกิจ"
        )
        self.send_reply(chat_id, msg)

    def _handle_opportunity(self, chat_id: str):
        user_id = "client_user"
        weights = self.sheets.get_user_mixed_portfolio(user_id)
        signals = self.sheets.get_latest_signals()
        quota = self.sheets.get_annual_quota_status(user_id)
        last_dt = self.sheets.get_last_rebalance_time(user_id)

        detector = OpportunityDetector(max_rebalances=12)
        opp = detector.evaluate_opportunity(weights, signals, quota["used"], last_dt)

        dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:3000")
        if opp["is_opportunity"]:
            msg = detector.format_alert_message(opp, dashboard_url=dashboard_url)
        else:
            msg = (
                f"ℹ️ *[สถานะการวิเคราะห์โอกาสการลงทุน]*\n\n"
                f"💡 {opp['reason']}\n\n"
                f"📊 สิทธิ์คงเหลือปีนี้: *{quota['remaining']}/{quota['max_allowed']} ครั้ง*\n"
                f"คะแนนพอร์ตปัจจุบันอยู่ในเกณฑ์ที่สมดุล ระบบกำลังติดตามการเคลื่อนไหวของตลาดอย่างต่อเนื่องครับ"
            )
        self.send_reply(chat_id, msg)

    def _handle_sync(self, chat_id: str):
        self.send_reply(chat_id, "🔄 กำลังเริ่มประมวลผลข้อมูลตลาดและคำนวณคะแนนใหม่ กรุณารอสักครู่ (ประมาณ 5-10 วินาที)...")
        try:
            from data_pipeline.pipeline import GPFPipeline
            pipeline = GPFPipeline(sheets_client=self.sheets)
            transitions = pipeline.run_daily_update(persist=False)
            
            self.send_reply(
                chat_id, 
                f"✅ ประมวลผลเสร็จเรียบร้อย! ตรวจพบสัญญาณเปลี่ยนสถานะ {len(transitions)} แผน\n"
                f"พิมพ์ `/status` เพื่อดูผลคะแนนล่าสุด หรือ `/opportunity` เพื่อดูคำแนะนำปรับพอร์ตครับ"
            )
        except Exception as e:
            logger.error(f"Error executing sync command via Telegram: {e}")
            self.send_reply(chat_id, f"⚠️ เกิดข้อผิดพลาดในการประมวลผล: {e}")

    def _handle_help(self, chat_id: str):
        msg = (
            "🤖 *ยินดีต้อนรับสู่ Gor.PF AI Advisor!*\n"
            "ระบบเฝ้าระวังตลาดและตรวจจับโอกาสทำกำไรสำหรับกองทุน กบข.\n\n"
            "💡 *คำสั่งที่คุณสามารถใช้งานได้:*\n"
            "👉 `/ping` หรือ `/check` - ตรวจสอบว่าระบบทำงานอยู่หรือไม่\n"
            "👉 `/status` - ดูสัญญาณและคะแนนจัดพอร์ตกองทุนปัจจุบัน\n"
            "👉 `/quota` - ตรวจสอบสิทธิ์เปลี่ยนแผน กบข. ประจำปี (12 ครั้ง/ปี)\n"
            "👉 `/opportunity` - ตรวจสอบโอกาสทำกำไรและคำแนะนำปรับพอร์ต\n"
            "👉 `/sync` - สั่งให้อัปเดตราคาตลาดและวิเคราะห์ใหม่ทันที\n"
            "👉 `/help` - แสดงคำสั่งช่วยเหลือนี้\n\n"
            "ระบบจะส่งแจ้งเตือนอัตโนมัติทันทีเมื่อมีโอกาสทำกำไรหรือมีสัญญาณลดความเสี่ยงครับ 🔔"
        )
        self.send_reply(chat_id, msg)

    def _handle_subscribe(self, chat_id: str, user_name: str = ""):
        self.sheets.add_subscriber(chat_id, platform="telegram", user_name=user_name)
        msg = (
            "🎉 *ยินดีต้อนรับสู่ Gor.PF AI Advisor!*\n\n"
            "✅ *ระบบได้ลงทะเบียนรับการแจ้งเตือนให้ท่านเรียบร้อยแล้ว!*\n"
            "ทุกครั้งที่ระบบตรวจพบโอกาสทำกำไร หรือสัญญาณลดความเสี่ยง ระบบจะส่งข้อความแจ้งเตือนมายังห้องแชตนี้โดยอัตโนมัติ 🚀\n\n"
            "💡 *คำสั่งที่คุณสามารถใช้งานได้ตลอด 24 ชม.:*\n"
            "👉 `/ping` : ตรวจสอบว่าระบบทำงานอยู่หรือไม่\n"
            "👉 `/status` : ดูสัญญาณตลาดและคะแนนของทุกแผน กบข.\n"
            "👉 `/quota` : ตรวจสอบสิทธิ์เปลี่ยนแผน กบข. ปี 2026 (12 ครั้ง/ปี)\n"
            "👉 `/opportunity` : ตรวจสอบโอกาสทำกำไรและคำแนะนำปรับพอร์ต\n"
            "👉 `/help` : แสดงรายการช่วยเหลือ\n\n"
            "ขอบคุณที่ไว้วางใจให้ Gor.PF เป็นผู้ช่วยติดตามพอร์ต กบข. ของท่านครับ"
        )
        self.send_reply(chat_id, msg)



def start_telegram_polling(handler: Optional[TelegramWebhookHandler] = None):
    """Runs a background polling loop to receive Telegram commands in local dev mode."""
    import threading
    import time
    
    handler = handler or TelegramWebhookHandler()
    if not handler.enabled:
        logger.info("Telegram Bot token missing. Polling service disabled.")
        return None
        
    def poll_loop():
        offset = 0
        token = handler.bot_token
        logger.info("Telegram Bot polling service started. Listening for commands on @Gor_Gpf_bot...")
        # Clear webhook first so getUpdates works
        try:
            requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook", timeout=5)
        except Exception:
            pass

        while True:
            try:
                url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=10"
                res = requests.get(url, timeout=15)
                if res.status_code == 200:
                    updates = res.json().get("result", [])
                    for u in updates:
                        offset = u["update_id"] + 1
                        handler.process_update(u)
                else:
                    time.sleep(3)
            except Exception as e:
                time.sleep(3)
                
    thread = threading.Thread(target=poll_loop, daemon=True)
    thread.start()
    return thread

