import os
import logging
import requests
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class TelegramBotNotifier:
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.bot_token and self.chat_id)
        
        if not self.enabled:
            logger.warning("Telegram Bot credentials missing. Telegram alerts will run in offline/logger mode.")

    def send_transition_alert(self, transitions: List[Dict[str, Any]]):
        """Sends transition alerts to the specified Telegram chat/channel."""
        if not self.enabled or not transitions:
            logger.info("Skipping Telegram alert: bot disabled or no transitions.")
            return

        for trans in transitions:
            plan_name = trans["plan_name"]
            old_signal = trans["old_signal"]
            new_signal = trans["new_signal"]
            score = trans["composite_score"]
            commentary = trans["thai_commentary"]
            
            # Map signals to emojis
            emojis = {
                "BUY_HOLD": "🟢",
                "WATCH": "🟡",
                "REDUCE": "🔴"
            }
            
            emoji_old = emojis.get(old_signal, "⚪")
            emoji_new = emojis.get(new_signal, "⚪")
            
            # Split commentary by lines (ensure up to 3 lines)
            commentary_lines = [line.strip() for line in commentary.split("\n") if line.strip()]
            while len(commentary_lines) < 3:
                commentary_lines.append("")

            message = (
                f"🔔 *[แจ้งเตือนสัญญาณปรับพอร์ต กบข.]*\n\n"
                f"*แผนการลงทุน:* {plan_name}\n"
                f"*การเปลี่ยนแปลง:* {emoji_old} {old_signal} ➔ {emoji_new} {new_signal}\n"
                f"*คะแนนรวมสุทธิ:* {score:.1f} / 100.0\n\n"
                f"*บทวิเคราะห์สภาวะตลาดกบข. โดย AI:*\n"
                f"1️⃣ {commentary_lines[0]}\n"
                f"2️⃣ {commentary_lines[1]}\n"
                f"3️⃣ {commentary_lines[2]}\n\n"
                f"🔗 [เปิดเว็บแอป Dashboard](https://gpf-smartinvestor.com)\n"
                f"⚠️ _คำเตือน: การลงทุนมีความเสี่ยง สัญญาณนี้ไม่ใช่คำแนะนำการลงทุนอย่างเป็นทางการ_"
            )
            
            recipients = self.get_recipients()
            for target_id in recipients:
                payload = {
                    "chat_id": target_id,
                    "text": message,
                    "parse_mode": "Markdown"
                }
                try:
                    res = requests.post(url, json=payload, timeout=10)
                    if res.status_code == 200:
                        logger.info(f"Successfully sent transition alert to Telegram chat: {target_id}")
                    else:
                        logger.error(f"Telegram API failed for {target_id}: {res.status_code} - {res.text}")
                except Exception as e:
                    logger.error(f"Error calling Telegram API for {target_id}: {e}")

    def get_recipients(self) -> List[str]:
        """Returns all subscriber chat IDs, guaranteeing default chat_id is included."""
        recipients = []
        if self.chat_id:
            recipients.append(str(self.chat_id))
        try:
            from data_pipeline.gspread_client import GPFSpreadsheetClient
            sheets = GPFSpreadsheetClient()
            subs = sheets.get_subscribers(platform="telegram")
            recipients.extend(subs)
        except Exception:
            pass
        return list(dict.fromkeys(recipients))

    def send_message(self, text: str) -> bool:
        """Sends a generic text message to all subscribers using the Telegram Bot API."""
        if not self.enabled:
            logger.info("Telegram Bot disabled. Skipping message.")
            return False
            
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        recipients = self.get_recipients()
        any_success = False

        for target_id in recipients:
            payload = {
                "chat_id": target_id,
                "text": text,
                "parse_mode": "Markdown"
            }
            try:
                res = requests.post(url, json=payload, timeout=10)
                if res.status_code == 200:
                    any_success = True
            except Exception as e:
                logger.error(f"Error calling Telegram API for {target_id}: {e}")

        return any_success

