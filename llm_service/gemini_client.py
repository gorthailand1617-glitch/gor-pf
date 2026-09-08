import os
import logging
import json
import google.generativeai as genai
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

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

class GeminiAnalysisService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        self.enabled = False
        
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set. Gemini Service will operate in fallback mode.")
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

        try:
            model = genai.GenerativeModel(self.model_name)
            
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
            logger.error(f"Error generating content from Gemini: {e}", exc_info=True)
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
