import os
import logging
import json

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai
except ImportError:
    genai = None
from typing import Dict, Any, List, Optional
try:
    from pydantic import BaseModel, Field
    class LLMAnalysisResponse(BaseModel):
        sentiment_modifier: float = Field(
            ..., 
            description="Sentiment modifier score from -15.0 to +15.0 based on news sentiment. positive for bullish macro news, negative for bearish."
        )
        anomaly_detected: bool = Field(
            ..., 
            description="Flag to indicate anomaly if technical indicators are strongly bullish but macro news is catastrophic, or vice versa."
        )
        thai_commentary: str = Field(
            ..., 
            description="Polite and concise advisory summary in Thai, exactly 3 lines, explaining current market state and rationale."
        )
except ImportError:
    class LLMAnalysisResponse:
        pass

class GeminiAnalysisService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self.enabled = False
        
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set. Gemini Service will operate in fallback mode.")
            return

        if not genai:
            logger.warning("google.generativeai package not installed. Gemini Service operating in fallback mode.")
            return

        try:
            genai.configure(api_key=self.api_key)
            self.enabled = True
            logger.info(f"Gemini API configured successfully using model: {self.model_name}")
        except Exception as e:
            logger.error(f"Error configuring Gemini API: {e}", exc_info=True)

    def analyze_market_sentiment(
        self, 
        plan_name: str,
        technical_score: float, 
        indicators: Dict[str, Any], 
        news_headlines: List[str]
    ) -> Dict[str, Any]:
        """
        Calls Gemini to get sentiment score, anomaly detection, and 3-line Thai commentary.
        """
        if not self.enabled:
            return self._get_fallback_response("offline_mode")
            
        headlines_str = "\n".join([f"- {h}" for h in news_headlines])
        
        prompt = f"""
You are an expert financial analyst and quantitative strategist for the Thailand Government Pension Fund (GPF).
Analyze the following asset allocation state and news headlines for the GPF Plan: "{plan_name}".

[TECHNICAL PARAMETERS]
- Technical Base Score (0-70 scale): {technical_score:.2f}
- Indicators: {json.dumps(indicators)}

[BREAKING NEWS HEADLINES]
{headlines_str}

[YOUR INSTRUCTIONS]
1. News Sentiment Modifier: Assess how the breaking news headlines impact the short-term outlook for this plan.
   Provide a score modifier from -15.0 (extremely bearish/negative macro impact) to +15.0 (extremely bullish/positive macro impact).
2. Anomaly Check: Determine if there is an anomaly or extreme contradiction. For example, if technical scores suggest a strong BUY but news indicates an imminent banking collapse.
3. Thai Commentary: Write a polite, professional, and clear investment advisory explanation in Thai.
   CRITICAL: It must be EXACTLY 3 lines of text. Do not output markdown, bullet points, or list structures. Just 3 distinct sentences/lines.

Ensure the return matches the JSON response schema.
"""

        import time
        model = genai.GenerativeModel(self.model_name)
        
        for attempt in range(2):
            try:
                # Request structured JSON matching the Pydantic schema
                response = model.generate_content(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        response_mime_type="application/json",
                        response_schema=LLMAnalysisResponse
                    )
                )
                
                result_dict = json.loads(response.text)
                logger.info(f"Successfully received analysis from Gemini: {result_dict}")
                return result_dict
            except Exception as e:
                err_msg = str(e)
                if "429" in err_msg and attempt == 0:
                    logger.warning("Gemini free tier rate limit reached, waiting 11s before retrying...")
                    time.sleep(11)
                    continue
                logger.error(f"Error generating content from Gemini: {e}")
                return self._get_fallback_response("api_error")
        return self._get_fallback_response("api_error")

    def _get_fallback_response(self, reason: str) -> Dict[str, Any]:
        """Helper to return fallback default values when LLM call fails."""
        if reason == "offline_mode":
            thai_commentary = (
                "ระบบกำลังทำงานในโหมดออฟไลน์ชั่วคราว\n"
                "สัญญาณในปัจจุบันคำนวณจากตัวชี้วัดทางเทคนิคและข้อมูลราคาตลาดหลักแบบเรียลไทม์\n"
                "กรุณาตรวจสอบการตั้งค่า API Key เพื่อเปิดใช้งานระบบการวิเคราะห์ข่าวสารโดยละเอียด"
            )
        else:
            thai_commentary = (
                "ระบบไม่สามารถเชื่อมต่อกับบริการวิเคราะห์ข่าวสารได้ในขณะนี้\n"
                "กำลังแสดงสัญญาณอ้างอิงจากตัวชี้วัดความเฉื่อยและโมเมนตัมตลาดทางเทคนิคเป็นหลัก\n"
                "กรุณาตรวจสอบสถานะระบบหรือทดลองใหม่อีกครั้งในภายหลัง"
            )
            
        return {
            "sentiment_modifier": 0.0,
            "anomaly_detected": False,
            "thai_commentary": thai_commentary
        }

    def analyze_portfolio_rebalance(
        self, 
        current_weights: Dict[str, float], 
        target_weights: Dict[str, float], 
        asset_signals: Dict[str, Dict[str, Any]]
    ) -> str:
        """
        Generates a 3-line Thai commentary explaining the portfolio rebalancing suggestions.
        """
        if not self.enabled:
            return (
                "สภาวะตลาดมีความผันผวน แนะนำปรับลดพอร์ตสินทรัพย์เสี่ยงและเพิ่มตราสารหนี้ระยะสั้นเพื่อความปลอดภัย\n"
                "โมเดลควอนท์เสนอแนะเพิ่มสัดส่วนทองคำและหุ้นต่างประเทศเนื่องจากแนวโน้มดัชนีส่งสัญญาณบวกต่อเนื่อง\n"
                "ควรจัดพอร์ตตามน้ำหนักใหม่เพื่อเพิ่มโอกาสทำกำไรระยะสั้นและลดความเสี่ยงจากการถดถอยของตลาดหุ้นไทย"
            )
            
        prompt = f"""
You are an expert financial advisor for the Thailand Government Pension Fund (GPF).
Analyze the proposed mixed portfolio rebalancing recommendations:

[CURRENT PORTFOLIO WEIGHTS]
{json.dumps(current_weights)}

[PROPOSED OPTIMIZED WEIGHTS]
{json.dumps(target_weights)}

[ASSET MARKET SIGNALS]
{json.dumps(asset_signals)}

Write a polite, professional advisory explanation in Thai detailing why this rebalancing is suggested.
CRITICAL: It must be EXACTLY 3 lines of text. Do not output markdown, bullet points, or list structures. Just 3 distinct sentences/lines.
"""
        try:
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content(prompt)
            text = response.text.strip()
            # Normalize to 3 lines
            lines = [line.strip() for line in text.split("\n") if line.strip()]
            if len(lines) < 3:
                # Pad if fewer than 3 lines
                while len(lines) < 3:
                    lines.append("กรุณาพิจารณาจัดพอร์ตตามสัดส่วนที่แนะนำเพื่อประโยชน์สูงสุดในการลงทุน")
            return "\n".join(lines[:3])
        except Exception as e:
            logger.error(f"Error in analyze_portfolio_rebalance: {e}")
            return (
                "แนะนำปรับสัดส่วนการลงทุนตามสัญญาณความเฉื่อยทางเทคนิคเพื่อป้องกันความผันผวนระยะสั้น\n"
                "ทำการเพิ่มสัดส่วนในสินทรัพย์ที่มีสัญญาณแรงซื้อเชิงบวกชัดเจน เช่น ทองคำ และหุ้นต่างประเทศ\n"
                "พร้อมทั้งทยอยปรับลดสัดส่วนของหุ้นไทยและกองทุนอสังหาริมทรัพย์ที่ยังอยู่ในกรอบแนวโน้มขาลง"
            )

    def _generate_rule_based_advice(
        self,
        user_question: str,
        current_weights: Dict[str, float],
        signals: Dict[str, Dict[str, Any]],
        quota_status: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        High-precision rule-based advisory engine for GPF that answers market state,
        asset rationale, and advice based on real quant signals and holdings.
        """
        q = user_question.lower().strip()
        asset_thai_names = {
            "fixed_income": "ตราสารหนี้",
            "money_market": "เงินฝาก/ตลาดเงิน",
            "thai_equity": "หุ้นไทย",
            "thai_property": "อสังหาฯ ไทย",
            "global_equity": "หุ้นต่างประเทศ",
            "global_debt": "ตราสารหนี้ต่างประเทศ",
            "gold": "ทองคำ"
        }

        # Identify top assets in user's portfolio
        held_assets = [(k, v) for k, v in current_weights.items() if v > 0.001]
        held_assets.sort(key=lambda x: x[1], reverse=True)

        # Market signals summary
        buy_assets = [asset_thai_names.get(k, k) for k, s in signals.items() if s.get("signal") == "BUY_HOLD"]
        watch_assets = [asset_thai_names.get(k, k) for k, s in signals.items() if s.get("signal") == "WATCH"]
        reduce_assets = [asset_thai_names.get(k, k) for k, s in signals.items() if s.get("signal") == "REDUCE"]

        # Case 0: Greetings & Social
        if any(w in q for w in ["สวัสดี", "หวัดดี", "hello", "hi", "ดีครับ", "ดีค่ะ", "เฮลโล", "เป็นไงบ้าง", "สบายดี"]):
            user_hold_text = ""
            if held_assets:
                top_k, top_w = held_assets[0]
                user_hold_text = f" ปัจจุบันคุณถือ *{asset_thai_names.get(top_k, top_k)}* เป็นหลัก ({top_w*100:.1f}%)"
            return (
                f"👋 สวัสดีครับ! ผมคือ **Gor.PF AI Advisor** ผู้ช่วยวิเคราะห์และดูแลพอร์ตการลงทุน กบข. ของคุณครับ 🤖✨\n\n"
                f"{user_hold_text}\n"
                f"วันนี้ต้องการให้ผมช่วยอะไรเป็นพิเศษไหมครับ? สามารถถามผมได้ทุกเรื่อง เช่น:\n"
                f"• 📊 _\"ตลาด กบข. วันนี้เป็นยังไงบ้าง\"_\n"
                f"• 🎯 _\"ควรปรับแผนการลงทุนตอนนี้ไหม\"_\n"
                f"• 🪙 _\"ทองคำน่าถือต่อไหม\"_\n"
                f"• 💼 _\"ดูพอร์ตของฉันหน่อย\"_\n\n"
                f"พิมพ์คำถามคุยกับผมได้เลย หรือพิมพ์ `/help` เพื่อดูคำสั่งทั้งหมดครับ 🚀"
            )

        # Case 0.1: Bot Identity & Capabilities
        if any(w in q for w in ["คุณคือใคร", "ทำอะไรได้", "ช่วยอะไรได้", "ใครสร้าง", "บอทคืออะไร", "คุณทำอะไร"]):
            return (
                "🤖 **[Gor.PF AI Advisor คือใครและช่วยอะไรคุณได้บ้าง?]**\n\n"
                "ผมคือระบบ AI ผู้ช่วยบริหารพอร์ตการลงทุน **กบข. (กองทุนบำเหน็จบำนาญข้าราชการ)** ที่ขับเคลื่อนด้วยโมเดลเชิงปริมาณ (Quantitative Model) ร่วมกับ Google Gemini AI ครับ 💡\n\n"
                "✨ **สิ่งที่ผมสามารถช่วยคุณได้:**\n"
                "1. 📈 **วิเคราะห์สัญญาณ 7 แผน กบข.:** ตรวจจับจังหวะซื้อ/ถือ/ลดความเสี่ยงแบบเรียลไทม์\n"
                "2. 🎯 **แจ้งเตือนโอกาสปรับพอร์ต (Rebalance):** แนะนำจังหวะหมุนเงินเพื่อเร่งทำกำไรและถนอมโควตา 12 ครั้ง/ปี\n"
                "3. 🛡️ **ระบบรักษาเงินต้น (Capital Preservation):** เตือนทันทีเมื่อสินทรัพย์เสี่ยงเข้าสู่แดนอันตราย\n"
                "4. 💬 **ตอบคำถามและปรึกษาการลงทุน:** อธิบายแนวโน้มตลาด ทองคำ หุ้นไทย หุ้นนอก อย่างเข้าใจง่าย\n\n"
                "ลองพิมพ์ถามคำถามที่สงสัยได้เลยครับ เช่น _\"ทองคำรอบนี้น่าซื้อมั้ย\"_ หรือพิมพ์ `/opportunity` เพื่อตรวจพอร์ตครับ!"
            )

        # Case 1: Market summary question ("ตลาดเป็นไง", "สภาวะตลาด", "ตลาดวันนี้", "สรุปตลาด")
        if any(w in q for w in ["ตลาด", "สภาวะ", "สถานการณ์", "ภาพรวม"]):
            lines = [
                "📊 *[สรุปสภาวะตลาดและคำแนะนำสำหรับ กบข. วันนี้]*\n",
                "ภาพรวมตลาดสินทรัพย์ กบข. ในปัจจุบันมีการแยกทิศทางอย่างชัดเจนครับ:"
            ]
            if buy_assets:
                lines.append(f"🟢 *สัญญาณบวกแข็งแกร่ง (BUY/HOLD):* {', '.join(buy_assets)} — โมเมนตัมราคายังคงเป็นขาขึ้นต่อเนื่อง มีแรงซื้อสนับสนุน")
            if watch_assets:
                lines.append(f"🟡 *สัญญาณรอจังหวะ (WATCH):* {', '.join(watch_assets)} — ราคายังแกว่งตัวในกรอบ ให้ถือครองอย่างระมัดระวัง")
            if reduce_assets:
                lines.append(f"🔴 *สัญญาณเตือนความเสี่ยง (REDUCE):* {', '.join(reduce_assets)} — แรงขายกดดันชัดเจน แนะนำลดสัดส่วนหรือหลีกเลี่ยงเพื่อปกป้องเงินต้น")

            lines.append("\n💼 *คำแนะนำสำหรับพอร์ตของคุณ:*")
            if held_assets:
                top_k, top_w = held_assets[0]
                top_name = asset_thai_names.get(top_k, top_k)
                lines.append(f"ปัจจุบันคุณถือ *{top_name}* มากที่สุด ({top_w * 100:.1f}%) ซึ่งเป็นสัดส่วนหลักที่ช่วยรักษาความมั่นคงของพอร์ต")

            lines.append("\n👉 พิมพ์ `/opportunity` เพื่อดูข้อเสนอการปรับสัดส่วนเพื่อเพิ่มผลตอบแทน")
            lines.append("👉 พิมพ์ `/status` เพื่อดูคะแนนสัญญาณทั้ง 7 แผนอย่างละเอียดครับ")
            return "\n".join(lines)

        # Case 2: Gold questions ("ทอง", "ทองคำ")
        if "ทอง" in q:
            gold_sig = signals.get("gold", {})
            gold_status = gold_sig.get("signal", "BUY_HOLD")
            gold_score = float(gold_sig.get("composite_score", 65.0))
            user_gold = current_weights.get("gold", 0.0) * 100
            status_emoji = "🟢" if gold_status == "BUY_HOLD" else ("🟡" if gold_status == "WATCH" else "🔴")
            return (
                f"🪙 *[การวิเคราะห์แผนทองคำ กบข.]*\n\n"
                f"• สถานะสัญญาณ: {status_emoji} *{gold_status}* (คะแนนโมเมนตัม `{gold_score:.1f}/100`)\n"
                f"• สัดส่วนในพอร์ตปัจจุบันของคุณ: *{user_gold:.1f}%*\n\n"
                f"💡 *มุมมองเชิงกลยุทธ์:*\n"
                f"ราคาทองคำในตลาดโลกยังมีแรงหนุนจากความไม่แน่นอนของเศรษฐกิจมหภาคและการกระจายทุนสำรองระหว่างประเทศ "
                f"การถือทองคำในพอร์ตประมาณ 5-15% ช่วยลดความผันผวนของพอร์ตโดยรวมได้ดีมากครับ\n\n"
                f"👉 พิมพ์ `/opportunity` เพื่อดูว่าสัดส่วนทองคำปัจจุบันของคุณเหมาะสมกับสภาวะตลาดรอบนี้แล้วหรือยังครับ"
            )

        # Case 3: Foreign equity ("หุ้นนอก", "หุ้นต่างประเทศ", "หุ้นโลก", "us", "sp500")
        if any(w in q for w in ["หุ้นนอก", "หุ้นต่างประเทศ", "หุ้นโลก", "us", "sp500", "spy"]):
            g_sig = signals.get("global_equity", {})
            sig = g_sig.get("signal", "BUY_HOLD")
            score = float(g_sig.get("composite_score", 60.0))
            status_emoji = "🟢" if sig == "BUY_HOLD" else ("🟡" if sig == "WATCH" else "🔴")
            return (
                f"🌍 *[การวิเคราะห์แผนหุ้นต่างประเทศ]*\n\n"
                f"• สัญญาณปัจจุบัน: {status_emoji} *{sig}* (คะแนน `{score:.1f}/100`)\n"
                f"• สินทรัพย์อ้างอิง: S&P500 (SPY 60%) และตลาดเกิดใหม่ (EEM 40%)\n\n"
                f"💡 *มุมมองเชิงกลยุทธ์:*\n"
                f"หุ้นต่างประเทศยังคงเป็นเครื่องยนต์สร้างผลตอบแทนหลักในระยะยาว "
                f"แม้จะมีความผันผวนระยะสั้น แต่การถือครองตามรอบสัญญาณเทคนิคช่วยสร้างผลตอบแทนชนะเงินเฟ้อได้ดีครับ\n\n"
                f"👉 พิมพ์ `/status` เพื่อดูเปรียบเทียบกับแผนการลงทุนอื่น"
            )

        # Case 4: Thai equity ("หุ้นไทย", "set", "set50")
        if any(w in q for w in ["หุ้นไทย", "set", "set50"]):
            t_sig = signals.get("thai_equity", {})
            sig = t_sig.get("signal", "WATCH")
            score = float(t_sig.get("composite_score", 45.0))
            status_emoji = "🟢" if sig == "BUY_HOLD" else ("🟡" if sig == "WATCH" else "🔴")
            return (
                f"🇹🇭 *[การวิเคราะห์แผนหุ้นไทย]*\n\n"
                f"• สัญญาณปัจจุบัน: {status_emoji} *{sig}* (คะแนน `{score:.1f}/100`)\n"
                f"• สินทรัพย์อ้างอิง: TDEX (ETF ดัชนี SET50)\n\n"
                f"💡 *มุมมองเชิงกลยุทธ์:*\n"
                f"ดัชนีหุ้นไทยยังมีความอ่อนไหวต่อกระแสเงินทุนต่างชาติและปัจจัยเศรษฐกิจภายในประเทศ "
                f"ระบบแนะนำให้จัดสรรในสัดส่วนที่พอเหมาะ และรอสัญญาณกลับตัวที่ชัดเจนก่อนเพิ่มน้ำหนักครับ"
            )

        # Case 5: Quota inquiries ("โควต้า", "โควตา", "สิทธิ์", "สิทธิ์เหลือ", "เปลี่ยนแผนได้กี่ครั้ง")
        if any(w in q for w in ["โควต้า", "โควตา", "สิทธิ์", "กี่ครั้ง", "เหลือเท่าไหร่"]):
            quota_text = ""
            if quota_status:
                used = quota_status.get("used", 0)
                rem = quota_status.get("remaining", 12)
                yr = quota_status.get("year", datetime.now().year)
                blocks = "🟩" * used + "⬜" * rem
                quota_text = (
                    f"• ประจำปี: `{yr}`\n"
                    f"• สิทธิ์ที่ใช้ไปแล้ว: *{used} / 12 ครั้ง*\n"
                    f"• สิทธิ์คงเหลือ: *{rem} ครั้ง*\n"
                    f"• แถบสิทธิ์: {blocks}\n\n"
                )
            return (
                f"🎯 *[ข้อมูลโควตาการเปลี่ยนแผน กบข.]*\n\n"
                f"{quota_text}"
                f"📌 *เกณฑ์ของ กบข.:* สมาชิกสามารถเปลี่ยนแผนการลงทุนได้สูงสุด **12 ครั้งต่อปีปฏิทิน**\n"
                f"ระบบ Gor.PF ออกแบบมาเพื่อช่วย **ถนอมโควตา** โดยจะแนะนำให้ปรับพอร์ตเฉพาะเมื่อคะแนนต่างเกินเกณฑ์คุ้มค่า หรือเมื่อมีความเสี่ยงร้ายแรงเท่านั้นครับ 🛡️\n\n"
                f"👉 หากคุณปรับแผนในแอป My GPF ไปแล้ว สามารถพิมพ์ `/confirm` หรือ `/setquota <จำนวนครั้ง>` เพื่ออัปเดตสิทธิ์ให้ตรงกันได้ทันทีครับ!"
            )

        # Case 6: Meaning of -8% ("ลด", "เปอร์เซ็นต์", "ความหมาย")
        if any(w in q for w in ["ลด", "-8", "หมายความ", "เข้าใจ"]):
            return (
                "💡 *[คำอธิบาย: การแจ้งเตือนลดสัดส่วน เช่น ลดทองคำ -8%]*\n\n"
                "หมายถึงการ **'ลดลง 8% ของพอร์ตรวม' (Percentage Points)** ไม่ใช่การลดจนเหลือ 8% ครับ เช่น:\n"
                "• เดิมถือทองคำ: `15%`\n"
                "• คำแนะนำลด `-8%`: ให้ปรับเหลือ `7%` ในแอป My GPF\n"
                "• แล้วนำเงินส่วนต่าง 8% นั้นไปกระจายเพิ่มในสินทรัพย์ที่ปลอดภัยกว่า เช่น ตลาดเงิน หรือตราสารหนี้ครับ 🚀"
            )

        # General Fallback with full context
        user_w_str = ", ".join([f"{asset_thai_names.get(k, k)} {v * 100:.1f}%" for k, v in held_assets])
        return (
            f"🤖 *[Gor.PF AI Advisor]*\n\n"
            f"ขอบคุณสำหรับคำถามครับ! สำหรับพอร์ตปัจจุบันของคุณ ({user_w_str}):\n\n"
            f"• ระบบวิเคราะห์สัญญาณตามแนวโน้มราคาและความเสี่ยงเชิงปริมาณแบบเรียลไทม์\n"
            f"• สินทรัพย์ที่มีสัญญาณเด่นในขณะนี้: {', '.join(buy_assets) if buy_assets else 'สินทรัพย์ปลอดภัย/ตลาดเงิน'}\n"
            f"• สิทธิ์การเปลี่ยนแผนปีนี้: ใช้ไปแล้ว {quota_status.get('used', 0) if quota_status else 0}/12 ครั้ง (คงเหลือ {quota_status.get('remaining', 12) if quota_status else 12} ครั้ง)\n\n"
            f"คุณสามารถถามคำถามเพิ่มเติมได้ตลอดเวลา เช่น:\n"
            f"• _\"ตลาดวันนี้เป็นไงบ้าง\"_\n"
            f"• _\"ทองคำน่าถือต่อมั้ย\"_\n"
            f"• _\"/opportunity\"_ เพื่อดูคำแนะนำปรับพอร์ตที่ดีที่สุดครับ 🚀"
        )

    def ask_portfolio_advisor(
        self,
        user_question: str,
        current_weights: Dict[str, float],
        signals: Dict[str, Dict[str, Any]],
        quota_status: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Conversational assistant answering the user's questions about their GPF portfolio, 
        signals, rationale behind recommendations, and quota status with multi-turn chat support.
        """
        # If enabled and genai package is present, attempt LLM call
        if self.enabled and genai:
            try:
                asset_thai_names = {
                    "fixed_income": "ตราสารหนี้",
                    "money_market": "เงินฝาก/ตลาดเงิน",
                    "thai_equity": "หุ้นไทย",
                    "thai_property": "อสังหาฯ ไทย",
                    "global_equity": "หุ้นต่างประเทศ",
                    "global_debt": "ตราสารหนี้ต่างประเทศ",
                    "gold": "ทองคำ"
                }

                weights_summary = []
                for k, v in current_weights.items():
                    name = asset_thai_names.get(k, k)
                    weights_summary.append(f"- {name}: {v * 100:.1f}%")

                signals_summary = []
                for k, s in signals.items():
                    name = asset_thai_names.get(k, k)
                    sig = s.get("signal", "WATCH")
                    score = s.get("composite_score", 50.0)
                    rsi = s.get("rsi", 50.0)
                    signals_summary.append(f"- {name}: สัญญาณ {sig} (คะแนน {score:.1f}/100, RSI: {rsi:.1f})")

                quota_str = "โควตาเปลี่ยนแผน กบข.: สูงสุด 12 ครั้งต่อปีปฏิทิน"
                if quota_status:
                    quota_str = f"โควตาเปลี่ยนแผนปี {quota_status.get('year')}: ใช้ไปแล้ว {quota_status.get('used')}/{quota_status.get('max_allowed')} ครั้ง (คงเหลือ {quota_status.get('remaining')} ครั้ง)"

                system_instruction = f"""คุณคือ "Gor.PF AI Advisor" (กอร์ พีเอฟ) ที่ปรึกษาการลงทุนอัจฉริยะส่วนตัวสำหรับสมาชิก กบข. (กองทุนบำเหน็จบำนาญข้าราชการ) ประเทศไทย
คุณมีบุคลิกฉลาดรอบรู้ เป็นมิตร สุภาพ คุยสนุก เห็นอกเห็นใจข้าราชการไทย และอธิบายเรื่องการเงินเข้าใจง่าย

[ข้อมูลพอร์ตปัจจุบันของสมาชิก]
{chr(10).join(weights_summary) if weights_summary else "ยังไม่ได้ระบุสัดส่วน (ใช้ค่าเริ่มต้นตลาดเงิน)"}

[สัญญาณตลาดและคะแนนความเฉื่อยล่าสุด (Quantitative Signals)]
{chr(10).join(signals_summary) if signals_summary else "สัญญาณตลาดอยู่ในเกณฑ์ปกติ"}

[สถานะสิทธิ์โควตาเปลี่ยนแผน กบข.]
{quota_str}

[หลักเกณฑ์และกติกาสำคัญของ กบข.]
1. สมาชิกเปลี่ยนแผนการลงทุนได้สูงสุด 12 ครั้งต่อปีปฏิทิน (ระบบ Gor.PF มุ่งเน้นถนอมโควตา จะปรับเมื่อคุ้มค่าจริงเท่านั้น)
2. แผนการลงทุนหลัก: เงินฝาก/ตลาดเงิน (พักเงิน ปลอดภัยสูงสุด), ตราสารหนี้ (รายได้สม่ำเสมอ), หุ้นต่างประเทศ (สร้างผลตอบแทนระยะยาว), ทองคำ (กันเงินเฟ้อ/วิกฤต), หุ้นไทย (เติบโตตามเศรษฐกิจไทย), อสังหาฯ ไทย (เงินปันผล)
3. สัญญาณของระบบ:
   - BUY_HOLD (🟢): โมเมนตัมขาขึ้น มีแรงซื้อหนุน แนะนำสะสมหรือถือครอง
   - WATCH (🟡): แนวโน้มทรงตัว ให้เฝ้าระวังอย่างระมัดระวัง
   - REDUCE (🔴): แนวโน้มขาลง มีความเสี่ยง แนะนำลดสัดส่วนหรือย้ายไปสินทรัพย์ปลอดภัยเพื่อรักษาเงินต้น
4. คำว่า "ลดทองคำ -8%" หมายถึงลดลง 8 จุดเปอร์เซ็นต์ของพอร์ตรวม เช่น จาก 15% เหลือ 7% ไม่ใช่ลดจนเหลือ 8%

[แนวทางการตอบ]
- ตอบเป็นภาษาไทยอย่างเป็นธรรมชาติ มีชีวิตชีวา เหมือนคุยกับผู้เชี่ยวชาญการลงทุนที่เป็นมิตร
- สามารถพูดคุยทั่วไป ทักทาย รับมุก ตอบคำถามเกี่ยวกับเศรษฐกิจ การเกษียณ และ กบข. ได้อย่างลื่นไหล
- ใช้ Emoji และจัดข้อความแบบ Markdown ให้สวยงาม อ่านง่ายบนมือถือ
- หากมีคำถามเกี่ยวกับพอร์ต ให้วิเคราะห์เชื่อมโยงกับพอร์ตจริงและคะแนนสัญญาณล่าสุดของสมาชิกเสมอ
- แนะนำคำสั่งช่วยเหลือที่เกี่ยวข้องเมื่อเหมาะสม เช่น `/opportunity` (ดูจังหวะปรับพอร์ต), `/status` (ดูสัญญาณทั้ง 7 แผน), `/myportfolio` (ดูสัดส่วนพอร์ต)"""

                model = genai.GenerativeModel(
                    self.model_name,
                    system_instruction=system_instruction
                )

                # Format conversation history
                formatted_history = []
                if conversation_history:
                    for turn in conversation_history[-8:]:  # Take last 8 turns
                        role = "user" if turn.get("role") in ["user", "human"] else "model"
                        text = turn.get("content") or turn.get("text") or ""
                        if text:
                            formatted_history.append({"role": role, "parts": [text]})

                chat = model.start_chat(history=formatted_history)
                response = chat.send_message(user_question)
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                logger.error(f"Error answering with Gemini API: {e}")

        # High-quality fallback using quantitative signals and user portfolio
        return self._generate_rule_based_advice(
            user_question=user_question,
            current_weights=current_weights,
            signals=signals,
            quota_status=quota_status
        )

