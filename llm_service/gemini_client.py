import os
import logging
import json
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

    def ask_portfolio_advisor(
        self,
        user_question: str,
        current_weights: Dict[str, float],
        signals: Dict[str, Dict[str, Any]],
        quota_status: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Conversational assistant answering the user's questions about their GPF portfolio, 
        signals, rationale behind recommendations, and quota status.
        """
        if not self.enabled:
            return (
                "ขออภัยครับ ขณะนี้ระบบตอบคำถาม AI ออฟไลน์ชั่วคราว "
                "ท่านสามารถตรวจสอบคำแนะนำปรับพอร์ตได้โดยพิมพ์ `/opportunity` "
                "หรือดูสถานะสัญญาณทั้งหมดโดยพิมพ์ `/status` ครับ"
            )

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
            signals_summary.append(f"- {name}: สัญญาณ {sig} (คะแนน {score:.1f}/100)")

        quota_str = ""
        if quota_status:
            quota_str = f"โควตาการเปลี่ยนแผนปี {quota_status.get('year')}: ใช้ไป {quota_status.get('used')}/{quota_status.get('max_allowed')} ครั้ง (คงเหลือ {quota_status.get('remaining')} ครั้ง)"

        prompt = f"""
You are "Gor.PF AI Advisor", a smart and friendly quantitative financial assistant for a member of the Thailand Government Pension Fund (GPF / กบข.).
Answer the user's question directly, clearly, politely, and informatively in Thai.

[USER'S CURRENT PORTFOLIO HOLDINGS]
{chr(10).join(weights_summary)}

[CURRENT MARKET SIGNALS & SCORES]
{chr(10).join(signals_summary)}

[QUOTA STATUS]
{quota_str}

[KEY DOMAIN KNOWLEDGE]
1. GPF (กบข.) allows switching investment plans up to 12 times per calendar year.
2. In Gor.PF, signals mean:
   - BUY_HOLD: Strong positive momentum and stable macro environment. Good to accumulate or hold.
   - WATCH: Trend is softening or neutral. Maintain cautious position.
   - REDUCE: Severe downward trend or high macro risk. Recommend trimming or cutting to 0% to protect principal.
3. When the bot says "ลดทองคำ -8%", it means reducing by 8 percentage points relative to total portfolio (e.g. from 15% down to 7%), NOT reducing until only 8% is left.
4. Keep the answer concise (2-4 paragraphs maximum), friendly, easy to understand for non-financial experts, and include helpful next steps or commands (such as `/opportunity`, `/myportfolio`).

[USER'S QUESTION]
"{user_question}"
"""
        try:
            model = genai.GenerativeModel(self.model_name)
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error answering user query with Gemini: {e}")
            return (
                "ขออภัยครับ เกิดข้อผิดพลาดในการประมวลผลคำตอบจาก AI "
                "ท่านสามารถพิมพ์ `/opportunity` เพื่อดูคำแนะนำปรับพอร์ตล่าสุด "
                "หรือพิมพ์ `/status` เพื่อดูคะแนนสัญญาณตลาดทั้ง 7 แผนได้ครับ"
            )

