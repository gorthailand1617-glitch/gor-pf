import os
import logging
import requests
from datetime import datetime
from typing import Dict, Any, Optional

import re
import json
from data_pipeline.gspread_client import GPFSpreadsheetClient
from quant_engine.rebalance_opportunity import OpportunityDetector, ASSET_NAMES
from llm_service.gemini_client import GeminiAnalysisService

logger = logging.getLogger(__name__)

# Thai alias mapping for assets
ASSET_ALIASES = {
    "ทองคำ": "gold",
    "ทอง": "gold",
    "gold": "gold",
    "หุ้นต่างประเทศ": "global_equity",
    "หุ้นตปท": "global_equity",
    "หุ้นนอก": "global_equity",
    "หุ้นโลก": "global_equity",
    "global_equity": "global_equity",
    "หุ้นไทย": "thai_equity",
    "set": "thai_equity",
    "thai_equity": "thai_equity",
    "ตราสารหนี้": "fixed_income",
    "พันธบัตร": "fixed_income",
    "fixed_income": "fixed_income",
    "เงินฝาก": "money_market",
    "ตลาดเงิน": "money_market",
    "ตราสารหนี้ระยะสั้น": "money_market",
    "money_market": "money_market",
    "อสังหา": "thai_property",
    "อสังหาริมทรัพย์": "thai_property",
    "กองทุนอสังหา": "thai_property",
    "thai_property": "thai_property",
    "ตราสารหนี้ต่างประเทศ": "global_debt",
    "ตราสารหนี้ตปท": "global_debt",
    "global_debt": "global_debt"
}


class TelegramWebhookHandler:
    def __init__(self, sheets_client: Optional[GPFSpreadsheetClient] = None, gemini_client: Optional[GeminiAnalysisService] = None):
        self._sheets = sheets_client
        self._gemini = gemini_client
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.allowed_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.bot_token)

    @property
    def sheets(self) -> GPFSpreadsheetClient:
        if self._sheets is None:
            self._sheets = GPFSpreadsheetClient()
        return self._sheets

    @property
    def gemini(self) -> GeminiAnalysisService:
        if self._gemini is None:
            self._gemini = GeminiAnalysisService()
        return self._gemini

    def send_reply(self, chat_id: str, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> bool:
        """Sends a text message back to the user via Telegram with optional inline keyboard."""
        if not self.bot_token:
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                return True
            # Fallback retry without Markdown
            logger.warning(f"send_reply Markdown failed ({res.status_code}): {res.text}. Retrying plain text...")
            plain_payload = {
                "chat_id": chat_id,
                "text": text.replace("*", "").replace("`", "").replace("_", "")
            }
            if reply_markup:
                plain_payload["reply_markup"] = reply_markup
            res_plain = requests.post(url, json=plain_payload, timeout=10)
            return res_plain.status_code == 200
        except Exception as e:
            logger.error(f"Error replying to Telegram chat {chat_id}: {e}")
            return False

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None):
        """Acknowledges a callback query from an inline keyboard button."""
        if not self.bot_token:
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logger.warning(f"Error answering callback query: {e}")

    def process_update(self, update: Dict[str, Any]):
        """Processes an incoming Telegram update object (Message or Callback Query)."""
        # 1. Handle Inline Button Click (callback_query)
        callback_query = update.get("callback_query")
        if callback_query:
            self._handle_callback_query(callback_query)
            return

        # 2. Handle Text Message
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
        elif cmd in ["/opportunity", "/rebalance"]:
            self._handle_opportunity(chat_id)
        elif cmd in ["/myportfolio", "/myport", "/port"]:
            self._handle_myportfolio(chat_id)
        elif cmd in ["/setport", "/updateport"]:
            self._handle_setport(chat_id, text)
        elif cmd in ["/confirm"]:
            self._handle_confirm_rebalance(chat_id)
        elif cmd in ["/sync"]:
            self._handle_sync(chat_id)
        elif cmd in ["/start", "/subscribe"]:
            self._handle_subscribe(chat_id, display_name)
        elif cmd in ["/help"]:
            self._handle_help(chat_id)
        else:
            # Check if user says something like "ตั้งพอร์ต..." or "พอร์ตฉัน..."
            if text.startswith("ตั้งพอร์ต") or text.startswith("ปรับพอร์ต"):
                self._handle_setport(chat_id, text)
            elif any(w in text for w in ["พอร์ตฉัน", "พอร์ตของฉัน", "ดูพอร์ต", "ถืออะไร"]):
                self._handle_myportfolio(chat_id)
            else:
                # Conversational AI fallback via Gemini
                self._handle_ai_chat(chat_id, text)

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
        try:
            from telegram_bot.notifier import TelegramBotNotifier
            notifier = TelegramBotNotifier(bot_token=self.bot_token, chat_id=chat_id)

            # 1. Check if we already have today's / latest signals in Google Sheets
            signals_dict = self.sheets.get_latest_signals()
            results = list(signals_dict.values()) if signals_dict else []

            # 2. If no saved signals exist, calculate dynamically
            if not results:
                self.send_reply(chat_id, "⏳ กำลังประมวลผลสรุปสภาวะตลาด กบข. ประจำวัน กรุณารอสักครู่...")
                from data_pipeline.pipeline import GPFPipeline
                pipeline = GPFPipeline(sheets_client=self.sheets)
                pipeline.run_daily_update(persist=False)
                results = pipeline.latest_results

            if results:
                success = notifier.send_daily_summary(results, target_chat_id=chat_id)
                if not success:
                    self.send_reply(chat_id, "⚠️ ไม่สามารถจัดส่งสรุปตลาดได้ในขณะนี้ กรุณาลองใหม่อีกครั้ง")
            else:
                self.send_reply(chat_id, "⚠️ ไม่สามารถประมวลผลข้อมูลตลาดได้ในขณะนี้ กรุณาลองพิมพ์ `/sync` เพื่อดึงข้อมูลใหม่")
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
            # Add interactive inline buttons
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "📋 ดูสัดส่วน My GPF", "callback_data": "btn_mygpf_weights"},
                        {"text": "💡 ทำไมต้องปรับ?", "callback_data": "btn_why_rebalance"}
                    ],
                    [
                        {"text": "✅ ฉันปรับใน กบข. เรียบร้อยแล้ว", "callback_data": "btn_confirm_rebalance"}
                    ]
                ]
            }
            self.send_reply(chat_id, msg, reply_markup=reply_markup)
        else:
            msg = (
                f"ℹ️ *[สถานะการวิเคราะห์โอกาสการลงทุน]*\n\n"
                f"💡 {opp['reason']}\n\n"
                f"📊 สิทธิ์คงเหลือปีนี้: *{quota['remaining']}/{quota['max_allowed']} ครั้ง*\n"
                f"คะแนนพอร์ตปัจจุบันอยู่ในเกณฑ์ที่สมดุล ระบบกำลังติดตามการเคลื่อนไหวของตลาดอย่างต่อเนื่องครับ"
            )
            reply_markup = {
                "inline_keyboard": [
                    [{"text": "💼 ดูพอร์ตปัจจุบันของฉัน", "callback_data": "btn_view_my_port"}]
                ]
            }
            self.send_reply(chat_id, msg, reply_markup=reply_markup)

    def _handle_myportfolio(self, chat_id: str):
        """Displays user's current saved portfolio allocation and calculated health score."""
        user_id = "client_user"
        weights = self.sheets.get_user_mixed_portfolio(user_id)
        signals = self.sheets.get_latest_signals()
        quota = self.sheets.get_annual_quota_status(user_id)

        detector = OpportunityDetector(max_rebalances=12)
        curr_score = detector.calculate_weighted_score(weights, signals) if signals else 50.0

        lines = [
            "💼 *[สัดส่วนพอร์ต กบข. ปัจจุบันของคุณในระบบ]*\n",
            f"📈 *คะแนนสุขภาพพอร์ต:* `{curr_score:.1f} / 100.0`",
            f"📊 *โควตาเปลี่ยนแผนปี {quota['year']}:* ใช้ไป {quota['used']}/{quota['max_allowed']} (เหลือ {quota['remaining']} ครั้ง)\n",
            "📌 *สัดส่วนการถือครอง:*"
        ]

        emojis = {"BUY_HOLD": "🟢", "WATCH": "🟡", "REDUCE": "🔴"}
        for asset_key, asset_name in ASSET_NAMES.items():
            w = weights.get(asset_key, 0.0) * 100
            sig_data = signals.get(asset_key, {})
            sig = sig_data.get("signal", "WATCH")
            emoji = emojis.get(sig, "⚪")
            lines.append(f"• {asset_name}: *{w:.1f}%* {emoji} `{sig}`")

        lines.append("\n💡 *วิธีแก้ไขสัดส่วนให้ตรงกับแอป My GPF:*")
        lines.append("พิมพ์: `/setport ทองคำ 10, หุ้นนอก 30, ตราสารหนี้ 40, ตลาดเงิน 20`")

        reply_markup = {
            "inline_keyboard": [
                [{"text": "🎯 เช็คโอกาสปรับพอร์ต", "callback_data": "btn_check_opp"}]
            ]
        }
        self.send_reply(chat_id, "\n".join(lines), reply_markup=reply_markup)

    def _handle_setport(self, chat_id: str, text: str):
        """
        Parses and updates the user's custom portfolio weights directly from chat.
        Usage: /setport ทองคำ 10, หุ้นนอก 30, ตราสารหนี้ 40, ตลาดเงิน 20
        """
        raw_input = text
        for prefix in ["/setport", "/updateport", "ตั้งพอร์ต", "ปรับพอร์ต"]:
            if raw_input.startswith(prefix):
                raw_input = raw_input[len(prefix):].strip()
                break

        if not raw_input:
            msg = (
                "ℹ️ *วิธีใช้งานคำสั่งตั้งค่าพอร์ต:*\n\n"
                "พิมพ์ระบุชื่อแผนและเปอร์เซ็นต์ (ผลรวมต้องได้ 100%) เช่น:\n"
                "`/setport ทองคำ 10, หุ้นนอก 30, ตราสารหนี้ 40, ตลาดเงิน 20`\n\n"
                "ชื่อแผนที่รองรับ: `ทองคำ`, `หุ้นนอก`, `หุ้นไทย`, `ตราสารหนี้`, `ตลาดเงิน`, `อสังหา`, `ตราสารหนี้ตปท`"
            )
            self.send_reply(chat_id, msg)
            return

        # Parse pairs using regex
        # Look for pattern: <name> <number>%? or <name>:<number>%?
        tokens = re.split(r"[,;\n]+", raw_input)
        new_weights: Dict[str, float] = {k: 0.0 for k in ASSET_NAMES.keys()}
        found_any = False

        for token in tokens:
            token = token.strip()
            if not token:
                continue
            match = re.search(r"([^\d:=]+)\s*[:=\s]\s*(\d+(?:\.\d+)?)%?", token)
            if match:
                raw_name = match.group(1).strip().lower()
                val = float(match.group(2))
                # Map to standard asset key
                matched_key = None
                for alias, asset_key in ASSET_ALIASES.items():
                    if alias in raw_name or raw_name in alias:
                        matched_key = asset_key
                        break
                if matched_key:
                    new_weights[matched_key] = val / 100.0 if val > 1.0 else val
                    found_any = True

        if not found_any:
            self.send_reply(
                chat_id, 
                "⚠️ ไม่สามารถอ่านรูปแบบสัดส่วนได้ กรุณาระบุ เช่น:\n`/setport ทองคำ 10, หุ้นนอก 30, ตราสารหนี้ 40, ตลาดเงิน 20`"
            )
            return

        total_sum = sum(new_weights.values())
        if abs(total_sum - 1.0) > 0.015:  # Tolerance within 1.5%
            self.send_reply(
                chat_id,
                f"⚠️ ผลรวมสัดส่วนต้องเท่ากับ 100% พอดี (สัดส่วนที่คุณระบุรวมได้: *{total_sum * 100:.1f}%*)\n"
                "กรุณาตรวจสอบตัวเลขอีกครั้งครับ"
            )
            return

        # Normalize to exactly 1.0
        normalized_weights = {k: round(v / total_sum, 3) for k, v in new_weights.items()}
        diff = 1.0 - sum(normalized_weights.values())
        if abs(diff) > 0.0001:
            max_key = max(normalized_weights, key=normalized_weights.get)
            normalized_weights[max_key] = round(normalized_weights[max_key] + diff, 3)

        # Save to Google Sheets
        user_id = "client_user"
        success = self.sheets.save_user_mixed_portfolio(user_id, normalized_weights)

        summary_lines = []
        for k, v in normalized_weights.items():
            if v > 0:
                summary_lines.append(f"• {ASSET_NAMES.get(k, k)}: `{v * 100:.1f}%`")

        msg = (
            "✅ *[บันทึกสัดส่วนพอร์ตใหม่เรียบร้อยแล้ว]*\n\n"
            "📋 *สัดส่วนพอร์ตที่บันทึก:*\n" +
            "\n".join(summary_lines) +
            "\n\nระบบจะนำสัดส่วนนี้ไปใช้เป็นฐานในการเฝ้าระวังและแจ้งเตือนโอกาส Rebalance ต่อไปครับ 🚀"
        )
        self.send_reply(chat_id, msg)

    def _handle_confirm_rebalance(self, chat_id: str):
        """Records that user has executed rebalance in My GPF, deducting 1 annual quota."""
        user_id = "client_user"
        quota = self.sheets.get_annual_quota_status(user_id)
        if quota["remaining"] <= 0:
            self.send_reply(chat_id, "⚠️ คุณใช้สิทธิ์เปลี่ยนแผนการลงทุนปีนี้ครบ 12 ครั้งแล้ว ไม่สามารถบันทึกเพิ่มได้ครับ")
            return

        weights = self.sheets.get_user_mixed_portfolio(user_id)
        signals = self.sheets.get_latest_signals()
        detector = OpportunityDetector(max_rebalances=12)
        opp = detector.evaluate_opportunity(weights, signals, quota["used"])

        opt_weights = opp.get("optimized_weights", weights)
        curr_score = opp.get("current_score", 50.0)
        opt_score = opp.get("optimized_score", 50.0)

        # 1. Update current portfolio weights to optimized
        self.sheets.save_user_mixed_portfolio(user_id, opt_weights)
        # 2. Record to Rebalance_Log
        self.sheets.record_rebalance_execution(
            user_id=user_id,
            old_weights=weights,
            new_weights=opt_weights,
            score_before=curr_score,
            score_after=opt_score,
            reason="บันทึกยืนยันผ่าน Telegram Bot",
            action_type="CONFIRMED"
        )

        new_quota = self.sheets.get_annual_quota_status(user_id)
        msg = (
            "🎉 *[บันทึกการปรับพอร์ต กบข. สำเร็จ]*\n\n"
            f"✅ อัปเดตสัดส่วนพอร์ตเป้าหมายใหม่เรียบร้อยแล้ว\n"
            f"📊 สิทธิ์การเปลี่ยนแผนปี {new_quota['year']}: "
            f"ใช้ไปแล้ว *{new_quota['used']}/{new_quota['max_allowed']}* ครั้ง "
            f"(คงเหลืออีก *{new_quota['remaining']}* ครั้ง)\n"
            f"📈 คะแนนประสิทธิภาพพอร์ตยกระดับเป็น: *{opt_score:.1f} / 100.0*\n\n"
            "ระบบจะเริ่มจับตาและคำนวณจากสัดส่วนใหม่นี้ทันทีครับ 🚀"
        )
        self.send_reply(chat_id, msg)

    def _handle_ai_chat(self, chat_id: str, user_question: str):
        """Natural conversational QA about GPF portfolio, market rationale, and terms."""
        user_id = "client_user"
        weights = self.sheets.get_user_mixed_portfolio(user_id)
        signals = self.sheets.get_latest_signals()
        quota = self.sheets.get_annual_quota_status(user_id)

        answer = self.gemini.ask_portfolio_advisor(
            user_question=user_question,
            current_weights=weights,
            signals=signals,
            quota_status=quota
        )
        self.send_reply(chat_id, answer)

    def _handle_callback_query(self, callback_query: Dict[str, Any]):
        """Handles button clicks on Telegram inline keyboards."""
        cb_id = callback_query.get("id")
        data = callback_query.get("data", "")
        message = callback_query.get("message", {})
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))

        self.answer_callback_query(cb_id, text="กำลังประมวลผล...")

        if data == "btn_mygpf_weights":
            # Show target weights formatted for typing into My GPF
            user_id = "client_user"
            weights = self.sheets.get_user_mixed_portfolio(user_id)
            signals = self.sheets.get_latest_signals()
            quota = self.sheets.get_annual_quota_status(user_id)
            detector = OpportunityDetector(max_rebalances=12)
            opp = detector.evaluate_opportunity(weights, signals, quota["used"])
            opt = opp.get("optimized_weights", weights)

            lines = ["📋 *[สัดส่วนสำหรับกรอกในแอป My GPF]*\n"]
            for a_key, a_name in ASSET_NAMES.items():
                w = opt.get(a_key, 0.0) * 100
                lines.append(f"• {a_name}: `{w:.1f}%`")
            lines.append("\nเปิดแอป My GPF ➔ เลือกเปลี่ยนแผน ➔ ระบุสัดส่วนตามนี้ได้เลยครับ")
            self.send_reply(chat_id, "\n".join(lines))

        elif data == "btn_why_rebalance":
            user_id = "client_user"
            weights = self.sheets.get_user_mixed_portfolio(user_id)
            signals = self.sheets.get_latest_signals()
            quota = self.sheets.get_annual_quota_status(user_id)
            detector = OpportunityDetector(max_rebalances=12)
            opp = detector.evaluate_opportunity(weights, signals, quota["used"])
            
            # Ask Gemini to explain why
            explanation = self.gemini.ask_portfolio_advisor(
                user_question=f"อธิบายเหตุผลอย่างละเอียดและเข้าใจง่ายว่าทำไมตอนนี้ระบบถึงมีคำแนะนำ: {opp.get('reason', '')}",
                current_weights=weights,
                signals=signals,
                quota_status=quota
            )
            self.send_reply(chat_id, f"💡 *[บทวิเคราะห์เหตุผลการปรับพอร์ต]:*\n\n{explanation}")

        elif data == "btn_confirm_rebalance":
            self._handle_confirm_rebalance(chat_id)

        elif data == "btn_view_my_port":
            self._handle_myportfolio(chat_id)

        elif data == "btn_check_opp":
            self._handle_opportunity(chat_id)

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
            "👉 `/myportfolio` หรือ `/port` - ดูสัดส่วนพอร์ต กบข. ปัจจุบันของคุณ\n"
            "👉 `/setport` - ตั้งค่าสัดส่วนพอร์ต เช่น `/setport ทองคำ 10, หุ้นนอก 30, ตราสารหนี้ 40, ตลาดเงิน 20`\n"
            "👉 `/opportunity` - ตรวจสอบโอกาสทำกำไรและคำแนะนำปรับพอร์ต\n"
            "👉 `/status` - ดูสัญญาณตลาดและคะแนนทั้ง 7 แผน\n"
            "👉 `/quota` - ตรวจสอบสิทธิ์เปลี่ยนแผน กบข. ประจำปี (12 ครั้ง/ปี)\n"
            "👉 `/confirm` - บันทึกยืนยันว่าปรับพอร์ตใน My GPF เรียบร้อยแล้ว\n"
            "👉 `/sync` - สั่งให้อัปเดตราคาตลาดและวิเคราะห์ใหม่ทันที\n"
            "👉 `/ping` - ตรวจสอบสถานะการทำงานของระบบ\n\n"
            "💬 *หรือพิมพ์ถามคำถามทั่วไปได้เลย!* เช่น:\n"
            "• _\"ทำไมถึงให้ลดทองคำ?\"_\n"
            "• _\"ตอนนี้หุ้นนอกยังน่าถืออยู่มั้ย?\"_\n"
            "• _\"ลดทอง -8% หมายความว่ายังไง?\"_"
        )
        self.send_reply(chat_id, msg)

    def _handle_subscribe(self, chat_id: str, user_name: str = ""):
        self.sheets.add_subscriber(chat_id, platform="telegram", user_name=user_name)
        msg = (
            "🎉 *ยินดีต้อนรับสู่ Gor.PF AI Advisor!*\n\n"
            "✅ *ระบบได้ลงทะเบียนรับการแจ้งเตือนให้ท่านเรียบร้อยแล้ว!*\n"
            "ทุกครั้งที่ระบบตรวจพบโอกาสทำกำไร หรือสัญญาณลดความเสี่ยง ระบบจะส่งข้อความแจ้งเตือนมายังห้องแชตนี้โดยอัตโนมัติ 🚀\n\n"
            "💡 *เริ่มต้นใช้งานง่ายๆ:*\n"
            "👉 พิมพ์ `/myportfolio` เพื่อดูพอร์ตของคุณ\n"
            "👉 หรือพิมพ์ถามคำถามเกี่ยวกับพอร์ต กบข. ได้ทันทีครับ"
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
                        threading.Thread(target=handler.process_update, args=(u,), daemon=True).start()
                else:
                    time.sleep(3)
            except Exception as e:
                time.sleep(3)
                
    thread = threading.Thread(target=poll_loop, daemon=True)
    thread.start()
    return thread

