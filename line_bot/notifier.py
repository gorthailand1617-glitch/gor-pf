import os
import logging
import requests
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

def create_flex_message(
    plan_name: str, 
    old_signal: str, 
    new_signal: str, 
    score: float, 
    commentary: str
) -> Dict[str, Any]:
    """Generates the LINE Flex Message JSON payload for a signal transition."""
    # Define colors for signals
    colors = {
        "BUY_HOLD": "#10b981", # Green
        "WATCH": "#f59e0b",    # Amber
        "REDUCE": "#ef4444"    # Red
    }
    
    color_old = colors.get(old_signal, "#6b7280")
    color_new = colors.get(new_signal, "#6b7280")
    
    # Split commentary by lines (ensure up to 3 lines)
    commentary_lines = [line.strip() for line in commentary.split("\n") if line.strip()]
    while len(commentary_lines) < 3:
        commentary_lines.append("")
        
    flex_content = {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "GPF SmartInvestor AI",
                    "weight": "bold",
                    "color": "#d97706",
                    "size": "sm"
                },
                {
                    "type": "text",
                    "text": "แจ้งเตือนการปรับพอร์ต กบข.",
                    "weight": "bold",
                    "size": "lg",
                    "margin": "md",
                    "color": "#1e293b"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": "แผนการลงทุน:",
                            "color": "#64748b",
                            "size": "sm",
                            "flex": 2
                        },
                        {
                            "type": "text",
                            "text": plan_name,
                            "weight": "bold",
                            "size": "sm",
                            "color": "#0f172a",
                            "flex": 3
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "md",
                    "contents": [
                        {
                            "type": "text",
                            "text": "การเปลี่ยนแปลง:",
                            "color": "#64748b",
                            "size": "sm",
                            "flex": 2
                        },
                        {
                            "type": "text",
                            "text": f"{old_signal} ➔ {new_signal}",
                            "weight": "bold",
                            "size": "sm",
                            "color": color_new,
                            "flex": 3
                        }
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "md",
                    "contents": [
                        {
                            "type": "text",
                            "text": "คะแนนรวม:",
                            "color": "#64748b",
                            "size": "sm",
                            "flex": 2
                        },
                        {
                            "type": "text",
                            "text": f"{score:.1f} / 100",
                            "weight": "bold",
                            "size": "sm",
                            "color": "#0f172a",
                            "flex": 3
                        }
                    ]
                },
                {
                    "type": "separator",
                    "margin": "lg"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "lg",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "text",
                            "text": "บทวิเคราะห์จาก AI:",
                            "weight": "bold",
                            "size": "sm",
                            "color": "#475569"
                        },
                        {
                            "type": "text",
                            "text": f"1. {commentary_lines[0]}",
                            "size": "xs",
                            "color": "#334155",
                            "wrap": True
                        },
                        {
                            "type": "text",
                            "text": f"2. {commentary_lines[1]}",
                            "size": "xs",
                            "color": "#334155",
                            "wrap": True
                        },
                        {
                            "type": "text",
                            "text": f"3. {commentary_lines[2]}",
                            "size": "xs",
                            "color": "#334155",
                            "wrap": True
                        }
                    ]
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "action": {
                        "type": "uri",
                        "label": "เปิดเว็บแอป Dashboard",
                        "uri": "https://gpf-smartinvestor.com" # Placeholder, user will configure
                    },
                    "style": "primary",
                    "color": "#d97706"
                },
                {
                    "type": "text",
                    "text": "คำเตือน: การลงทุนมีความเสี่ยง สัญญาณนี้ไม่ใช่คำแนะนำการลงทุนอย่างเป็นทางการ",
                    "size": "xxs",
                    "color": "#94a3b8",
                    "align": "center",
                    "margin": "md",
                    "wrap": True
                }
            ]
        }
    }
    return flex_content

class LINEBotNotifier:
    def __init__(self, access_token: Optional[str] = None, channel_secret: Optional[str] = None):
        self.access_token = access_token or os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
        self.channel_secret = channel_secret or os.getenv("LINE_CHANNEL_SECRET")
        self.enabled = bool(self.access_token and self.channel_secret)
        
        if not self.enabled:
            logger.warning("LINE Bot credentials missing. Broadcasts and webhook responses will run in offline/logger mode.")

    def broadcast_transitions(self, transitions: List[Dict[str, Any]], subscriber_ids: List[str]):
        """Broadcasts transition alerts to subscribers using LINE push messaging API."""
        if not self.enabled or not transitions or not subscriber_ids:
            logger.info("Skipping LINE broadcast: either bot disabled or empty list.")
            return

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}"
        }

        for trans in transitions:
            flex_msg = create_flex_message(
                plan_name=trans["plan_name"],
                old_signal=trans["old_signal"],
                new_signal=trans["new_signal"],
                score=trans["composite_score"],
                commentary=trans["thai_commentary"]
            )
            
            payload = {
                "to": "", # will be filled for each subscriber
                "messages": [
                    {
                        "type": "flex",
                        "altText": f"แจ้งเตือนสัญญาณปรับพอร์ต: {trans['plan_name']}",
                        "contents": flex_msg
                    }
                ]
            }
            
            for user_id in subscriber_ids:
                payload["to"] = user_id
                try:
                    res = requests.post(
                        "https://api.line.me/v2/bot/message/push",
                        json=payload,
                        headers=headers,
                        timeout=10
                    )
                    if res.status_code == 200:
                        logger.info(f"Successfully sent transition alert to LINE user: {user_id}")
                    else:
                        logger.error(f"LINE push API failed for user {user_id}: {res.status_code} - {res.text}")
                except Exception as e:
                    logger.error(f"Error calling LINE push API: {e}")
