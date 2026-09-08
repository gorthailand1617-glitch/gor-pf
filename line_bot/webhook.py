import os
import logging
import json
import hmac
import hashlib
import base64
import requests
from typing import Dict, Any, Optional
from fastapi import Request, Header, HTTPException

from data_pipeline.gspread_client import GPFSpreadsheetClient
from line_bot.notifier import create_flex_message

logger = logging.getLogger(__name__)

class LINEWebhookHandler:
    def __init__(self, sheets_client: Optional[GPFSpreadsheetClient] = None):
        self.sheets = sheets_client or GPFSpreadsheetClient()
        self.access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        self.channel_secret = os.getenv("LINE_CHANNEL_SECRET")
        self.enabled = bool(self.access_token and self.channel_secret)

    def verify_signature(self, body: str, signature: str) -> bool:
        """Verifies LINE webhook signature."""
        if not self.channel_secret:
            return True # skip signature check in dev/offline
        
        hash = hmac.new(
            self.channel_secret.encode('utf-8'),
            body.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        calculated_signature = base64.b64encode(hash).decode('utf-8')
        return hmac.compare_digest(calculated_signature, signature)

    async def handle_request(self, request: Request, x_line_signature: Optional[str] = Header(None)) -> Dict[str, Any]:
        """FastAPI route handler for LINE webhook events."""
        body = await request.body()
        body_str = body.decode("utf-8")

        if not self.enabled:
            logger.warning("LINE Webhook triggered but credentials are not set. Logging body for debugging:")
            logger.warning(body_str)
            return {"status": "ok", "message": "LINE bot disabled"}

        if not x_line_signature:
            logger.error("Missing X-Line-Signature header.")
            raise HTTPException(status_code=400, detail="Missing X-Line-Signature")

        if not self.verify_signature(body_str, x_line_signature):
            logger.error("Invalid LINE signature verification failed.")
            raise HTTPException(status_code=400, detail="Invalid signature")

        try:
            data = json.loads(body_str)
            events = data.get("events", [])
            for event in events:
                self._process_event(event)
        except Exception as e:
            logger.error(f"Error parsing LINE webhook events: {e}", exc_info=True)
            
        return {"status": "ok"}

    def _process_event(self, event: Dict[str, Any]):
        event_type = event.get("type")
        reply_token = event.get("replyToken")
        source = event.get("source", {})
        user_id = source.get("userId")

        if not reply_token or not user_id:
            return

        if event_type == "message":
            message = event.get("message", {})
            msg_text = message.get("text", "").strip().lower()
            
            if msg_text == "/status":
                self._handle_status_cmd(reply_token)
            elif msg_text == "/quota":
                self._handle_quota_cmd(reply_token, user_id)
            elif msg_text == "/opportunity":
                self._handle_opportunity_cmd(reply_token, user_id)
            elif msg_text == "/subscribe":
                self._handle_subscribe_cmd(reply_token, user_id)
            elif msg_text == "/unsubscribe":
                self._handle_unsubscribe_cmd(reply_token, user_id)
            else:
                self._handle_help_cmd(reply_token)
        elif event_type == "follow":
            self._handle_welcome_msg(reply_token)

    def _reply_to_user(self, reply_token: str, messages: list):
        """Calls LINE Reply Message API."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }
        payload = {
            "replyToken": reply_token,
            "messages": messages
        }
        try:
            res = requests.post(
                "https://api.line.me/v2/bot/message/reply",
                json=payload,
                headers=headers,
                timeout=10
            )
            if res.status_code != 200:
                logger.error(f"LINE Reply API error: {res.status_code} - {res.text}")
        except Exception as e:
            logger.error(f"Error calling LINE Reply API: {e}")

    def _handle_status_cmd(self, reply_token: str):
        """Sends the current state of the main plan to user via a Flex Message."""
        latest_signals = self.sheets.get_latest_signals()
        
        # Look for "main" plan or fallback to whatever plan is available
        plan_id = "main"
        plan_data = latest_signals.get(plan_id)
        
        if not plan_data and latest_signals:
            # Fallback to the first available plan
            plan_id = list(latest_signals.keys())[0]
            plan_data = latest_signals[plan_id]

        if not plan_data:
            # If no signals exist yet
            msg = {
                "type": "text",
                "text": "ยังไม่มีข้อมูลสัญญาณจัดพอร์ตในระบบขณะนี้ กรุณารัน Pipeline ประมวลผลก่อน"
            }
            self._reply_to_user(reply_token, [msg])
            return

        # Fetch plan name from config
        plan_name = "Plan หลัก (Mixed Assets)"
        if plan_id == "thai_equity":
            plan_name = "Plan หุ้นไทย"
        elif plan_id == "global_equity":
            plan_name = "Plan หุ้นต่างประเทศ"
        elif plan_id == "thai_property":
            plan_name = "Plan อสังหาริมทรัพย์ไทย"

        flex_bubble = create_flex_message(
            plan_name=plan_name,
            old_signal="-",
            new_signal=plan_data.get("signal", "WATCH"),
            score=float(plan_data.get("composite_score", 50.0)),
            commentary=plan_data.get("thai_commentary", "")
        )

        msg = {
            "type": "flex",
            "altText": f"สัญญาณจัดพอร์ตล่าสุด: {plan_name}",
            "contents": flex_bubble
        }
        self._reply_to_user(reply_token, [msg])

    def _handle_subscribe_cmd(self, reply_token: str, user_id: str):
        success = self.sheets.subscribe_user(user_id)
        if success:
            text = (
                "🟢 สมัครรับการแจ้งเตือนสัญญาณปรับพอร์ต กบข. สำเร็จ!\n"
                "ระบบจะส่งการแจ้งเตือนในรูปแบบ LINE Flex Message อัตโนมัติทุกครั้งเมื่อมีการขยับเกณฑ์สัญญาณจัดพอร์ตใหม่ (BUY_HOLD / WATCH / REDUCE)"
            )
        else:
            text = "🔴 ขออภัย ทำรายการไม่สำเร็จ กรุณาตรวจสอบสถานะระบบฐานข้อมูลของ Google Sheets หรือลองใหม่อีกครั้ง"
            
        self._reply_to_user(reply_token, [{"type": "text", "text": text}])

    def _handle_unsubscribe_cmd(self, reply_token: str, user_id: str):
        success = self.sheets.unsubscribe_user(user_id)
        if success:
            text = "🟡 ยกเลิกการรับแจ้งเตือนความเคลื่อนไหวสัญญาณจัดพอร์ตเรียบร้อยแล้ว คุณสามารถกลับมาเปิดใช้งานอีกครั้งได้เสมอโดยพิมพ์ /subscribe"
        else:
            text = "🔴 ไม่พบข้อมูลประวัติการติดตามของคุณ หรือ เกิดข้อผิดพลาดทางเทคนิคในฐานข้อมูล"
            
        self._reply_to_user(reply_token, [{"type": "text", "text": text}])

    def _handle_quota_cmd(self, reply_token: str, user_id: str):
        """Replies with current annual rebalance quota status."""
        quota = self.sheets.get_annual_quota_status(user_id)
        text = (
            f"📊 [สิทธิ์การเปลี่ยนแผนการลงทุน กบข.]\n\n"
            f"• ปีปฏิทิน: {quota['year']}\n"
            f"• สิทธิ์ทั้งหมด: {quota['max_allowed']} ครั้งต่อปี\n"
            f"• ปรับไปแล้ว: {quota['used']} ครั้ง\n"
            f"• คงเหลือ: {quota['remaining']} ครั้ง\n"
            f"• ปรับล่าสุดเมื่อ: {quota['last_rebalance'] or 'ยังไม่มีประวัติในปีนี้'}\n\n"
            f"💡 ตามเกณฑ์ กบข. สมาชิกสามารถเปลี่ยนแผนได้สูงสุด 12 ครั้งต่อปีปฏิทิน"
        )
        self._reply_to_user(reply_token, [{"type": "text", "text": text}])

    def _handle_opportunity_cmd(self, reply_token: str, user_id: str):
        """Checks for active profit opportunities."""
        from quant_engine.rebalance_opportunity import OpportunityDetector
        weights = self.sheets.get_user_mixed_portfolio(user_id)
        signals = self.sheets.get_latest_signals()
        quota = self.sheets.get_annual_quota_status(user_id)
        last_dt = self.sheets.get_last_rebalance_time(user_id)

        detector = OpportunityDetector(max_rebalances=12)
        opp = detector.evaluate_opportunity(weights, signals, quota["used"], last_dt)

        if opp["is_opportunity"]:
            dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:3000")
            msg_text = detector.format_alert_message(opp, dashboard_url=dashboard_url)
        else:
            msg_text = (
                f"ℹ️ [สถานะโอกาสการลงทุน]\n\n"
                f"{opp['reason']}\n\n"
                f"📊 สิทธิ์คงเหลือ: {quota['remaining']}/{quota['max_allowed']} ครั้ง\n"
                f"ระบบกำลังติดตามความเคลื่อนไหวของตลาดอย่างต่อเนื่อง"
            )
        self._reply_to_user(reply_token, [{"type": "text", "text": msg_text}])

    def _handle_welcome_msg(self, reply_token: str):
        text = (
            "ยินดีต้อนรับสู่บริการ GPF-SmartInvestor-AI!\n\n"
            "พิมพ์คำสั่งดังต่อไปนี้เพื่อเริ่มต้นงาน:\n"
            "👉 /status : ดูความเคลื่อนไหวสัญญาณล่าสุด\n"
            "👉 /quota : ตรวจสอบสิทธิ์เปลี่ยนแผน กบข. ประจำปี (12 ครั้ง/ปี)\n"
            "👉 /opportunity : ตรวจสอบโอกาสทำกำไรและคำแนะนำปรับพอร์ต\n"
            "👉 /subscribe : ติดตามรับการแจ้งเตือนอัตโนมัติ\n"
            "👉 /unsubscribe : ยกเลิกบริการรับแจ้งเตือน"
        )
        self._reply_to_user(reply_token, [{"type": "text", "text": text}])

    def _handle_help_cmd(self, reply_token: str):
        text = (
            "💡 คำสั่งที่รองรับ:\n"
            "👉 /status - แสดงสัญญาณและคะแนนจัดพอร์ตกองทุนปัจจุบัน\n"
            "👉 /quota - ตรวจสอบสิทธิ์เปลี่ยนแผน กบข. ประจำปี (12 ครั้ง/ปี)\n"
            "👉 /opportunity - ตรวจสอบโอกาสทำกำไรและคำแนะนำปรับพอร์ต\n"
            "👉 /subscribe - เปิดแจ้งเตือนอัตโนมัติเมื่อมีโอกาสสร้างกำไร\n"
            "👉 /unsubscribe - ปิดรับบริการการแจ้งเตือน"
        )
        self._reply_to_user(reply_token, [{"type": "text", "text": text}])

