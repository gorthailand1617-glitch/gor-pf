import os
import logging
import requests
from datetime import datetime
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

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
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

    def send_daily_summary(self, results: List[Dict[str, Any]], commentary: Optional[str] = None) -> bool:
        """Sends daily market summary of all GPF plans to Telegram subscribers."""
        if not self.enabled or not results:
            logger.info("Skipping daily summary: bot disabled or no results.")
            return False

        today_str = datetime.now().strftime("%d/%m/%Y")
        lines = [
            f"📊 *[รายงานสรุปสภาวะตลาด กบข. ประจำวัน]*",
            f"📅 ประจำวันที่: `{today_str}`",
            "───────────────────",
            "📌 *สรุปสัญญาณและคะแนนทั้ง 7 แผน:*"
        ]

        emojis = {
            "BUY_HOLD": "🟢 ซื้อ/ถือต่อ",
            "WATCH": "🟡 เฝ้าระวัง",
            "REDUCE": "🔴 ลดสัดส่วน"
        }

        plan_names = {
            "fixed_income": "ตราสารหนี้",
            "money_market": "ตลาดเงิน",
            "thai_equity": "หุ้นไทย",
            "thai_property": "อสังหาฯ ไทย",
            "global_equity": "หุ้นต่างประเทศ",
            "global_debt": "ตราสารหนี้ ตปท.",
            "gold": "ทองคำ"
        }

        top_commentary = []
        for r in results:
            p_id = r.get("plan_id", "")
            p_name = plan_names.get(p_id, r.get("plan_name", p_id))
            sig = r.get("signal", "WATCH")
            score = float(r.get("composite_score", 50.0))
            sig_text = emojis.get(sig, sig)
            daily_ret = r.get("daily_return")
            ret_text = ""
            if daily_ret is not None:
                ret_pct = float(daily_ret) * 100
                ret_icon = "🔺" if ret_pct > 0 else ("🔻" if ret_pct < 0 else "▫️")
                ret_text = f" ({ret_icon}{ret_pct:+.2f}%)"
            lines.append(f"• *{p_name}*: {sig_text} `{score:.1f}/100`{ret_text}")

            comm = r.get("thai_commentary", "").strip()
            if comm and len(top_commentary) < 2 and p_id in ["thai_equity", "global_equity", "gold"]:
                first_line = comm.split("\n")[0].strip()
                if first_line:
                    top_commentary.append(f"• *{p_name}*: {first_line}")

        lines.append("───────────────────")
        if commentary:
            lines.append(f"🧠 *มุมมองสภาวะตลาดโดย AI:*\n{commentary}")
        elif top_commentary:
            lines.append("🧠 *ไฮไลต์มุมมองสภาวะตลาด (AI):*")
            lines.extend(top_commentary)

        dashboard_url = os.getenv("DASHBOARD_URL", "http://localhost:3000")
        lines.append(f"\n🔗 [เปิดเว็บ Dashboard พอร์ต กบข.]({dashboard_url})")
        lines.append("⚠️ _ข้อมูลนี้เป็นการวิเคราะห์เชิงสถิติ ไม่ใช่คำแนะนำทางการเงินอย่างเป็นทางการ_")

        msg = "\n".join(lines)
        return self.send_message(msg)

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

