import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from data_pipeline.gspread_client import GPFSpreadsheetClient
from data_pipeline.market_data import MarketDataService
from quant_engine.metrics import calculate_indicators
from quant_engine.scoring import calculate_base_score
from llm_service.gemini_client import GeminiAnalysisService

logger = logging.getLogger(__name__)

# Fallback configurations in case Google Sheets is not connected/configured
DEFAULT_PLANS = {
    "main": {
        "name_th": "Plan หลัก (Mixed Assets)",
        "weights": {
            "TDEX.BK": 0.10,
            "SPY": 0.20,
            "EEM": 0.05,
            "WHART.BK": 0.10,
            "FIXED_INCOME_YIELD": 0.55
        }
    },
    "thai_equity": {
        "name_th": "Plan หุ้นไทย",
        "weights": {
            "TDEX.BK": 1.00
        }
    },
    "global_equity": {
        "name_th": "Plan หุ้นต่างประเทศ",
        "weights": {
            "SPY": 0.60,
            "EEM": 0.40
        }
    },
    "thai_property": {
        "name_th": "Plan อสังหาริมทรัพย์ไทย",
        "weights": {
            "WHART.BK": 1.00
        }
    },
    "fixed_income": {
        "name_th": "แผนตราสารหนี้",
        "weights": {
            "ABFTH.BK": 1.00
        }
    },
    "money_market": {
        "name_th": "แผนเงินฝากและตราสารหนี้ระยะสั้น",
        "weights": {
            "FIXED_INCOME_YIELD": 1.00
        }
    },
    "global_debt": {
        "name_th": "แผนตราสารหนี้ต่างประเทศ",
        "weights": {
            "BND": 1.00
        }
    },
    "gold": {
        "name_th": "แผนทองคำ",
        "weights": {
            "GLD": 1.00
        }
    }
}

class GPFPipeline:
    def __init__(
        self,
        sheets_client: Optional[GPFSpreadsheetClient] = None,
        market_service: Optional[MarketDataService] = None,
        gemini_service: Optional[GeminiAnalysisService] = None
    ):
        self.sheets = sheets_client or GPFSpreadsheetClient()
        self.market = market_service or MarketDataService()
        self.gemini = gemini_service or GeminiAnalysisService()
        self.latest_results = []

    def run_daily_update(self, persist: bool = True) -> List[Dict[str, Any]]:
        """
        Main orchestration function.
        1. Fetch weights & active plans
        2. Download historical proxy data (last 120 days)
        3. Save proxy prices to sheets (if persist=True)
        4. Calculate synthetic returns & technical indicators
        5. Run Gemini LLM sentiment and commentary
        6. Compute composite score & output signals
        7. Save signals to sheets (if persist=True)
        8. Return any status transitions for alert broadcasts.
        """
        logger.info("Starting GPF-SmartInvestor-AI update pipeline...")
        
        # 1. Fetch weights
        plan_weights = {}
        plan_names = {}
        if self.sheets.is_connected():
            plan_weights = self.sheets.get_plan_weights()
            # Fetch names from spreadsheet Config worksheet
            try:
                records = self.sheets.sh.worksheet("Config").get_all_records()
                for r in records:
                    plan_names[r["plan_id"]] = r["plan_name_th"]
            except Exception as e:
                logger.warning(f"Could not read plan names from Config worksheet: {e}")
        
        # Supplement missing default plans so all 7 GPF asset plans are always monitored
        for p_id, details in DEFAULT_PLANS.items():
            if p_id not in plan_weights:
                plan_weights[p_id] = details["weights"]
            if p_id not in plan_names:
                plan_names[p_id] = details["name_th"]

        # Get unique tickers
        all_tickers = set()
        for weights in plan_weights.values():
            all_tickers.update(weights.keys())
        
        # 2. Download historical data (120 days lookback to stabilize MA, RSI, MACD)
        start_date = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")
        prices_df = self.market.fetch_historical_prices(list(all_tickers), start_date, end_date)
        
        if prices_df.empty:
            logger.error("No historical price data could be downloaded. Aborting pipeline.")
            return []

        # 3. Save new proxy prices to Sheets
        if persist and self.sheets.is_connected():
            self._sync_proxy_prices_sheet(prices_df)

        # Get latest saved signals for transition checks
        prev_signals = {}
        if self.sheets.is_connected():
            prev_signals = self.sheets.get_latest_signals()

        news_headlines = []
        # Download news only once to conserve API calls
        try:
            news_headlines = self.market.fetch_market_news()
            logger.info(f"Retrieved {len(news_headlines)} headlines for LLM sentiment validation.")
        except Exception as e:
            logger.warning(f"Error fetching news headlines: {e}")

        pipeline_results = []
        transitions = []

        # 4. Compute synthetic indicators & signals for each plan
        for plan_id, weights in plan_weights.items():
            plan_name = plan_names.get(plan_id, plan_id)
            logger.info(f"Processing Plan: {plan_name} ({plan_id})...")
            
            # Filter prices_df to only tickers in this plan
            plan_tickers = list(weights.keys())
            plan_prices = prices_df[plan_tickers].copy()
            
            # Calculate technical metrics
            indicators_df = calculate_indicators(plan_prices, weights)
            if indicators_df.empty:
                logger.error(f"Failed to calculate indicators for plan: {plan_id}")
                continue
                
            # Base technical score on latest row
            latest_row = indicators_df.iloc[-1]
            base_score = calculate_base_score(indicators_df)
            
            # Format indicators payload for Gemini context
            indicators_context = {
                "synthetic_nav": float(latest_row["synthetic_nav"]),
                "daily_return": float(latest_row["daily_return"]),
                "ma20": float(latest_row["ma20"]),
                "ma60": float(latest_row["ma60"]),
                "rsi": float(latest_row["rsi"]),
                "macd": float(latest_row["macd"]),
                "macd_signal": float(latest_row["macd_signal"]),
                "volatility": float(latest_row["volatility"])
            }
            
            # 5. Gemini LLM verification
            llm_result = self.gemini.analyze_market_sentiment(
                plan_name=plan_name,
                technical_score=base_score,
                indicators=indicators_context,
                news_headlines=news_headlines
            )
            
            # Calculate composite score
            sentiment_mod = float(llm_result.get("sentiment_modifier", 0.0))
            composite_score = min(max(base_score + sentiment_mod, 0.0), 100.0)
            
            # Classify signal
            if composite_score >= 70.0:
                signal = "BUY_HOLD"
            elif composite_score >= 45.0:
                signal = "WATCH"
            else:
                signal = "REDUCE"
                
            latest_date_str = indicators_df.index[-1].strftime("%Y-%m-%d")
            
            record = {
                "date": latest_date_str,
                "plan_id": plan_id,
                "synthetic_nav": float(latest_row["synthetic_nav"]),
                "daily_return": float(latest_row["daily_return"]),
                "ma20": float(latest_row["ma20"]),
                "ma60": float(latest_row["ma60"]),
                "rsi": float(latest_row["rsi"]),
                "macd": float(latest_row["macd"]),
                "macd_signal": float(latest_row["macd_signal"]),
                "volatility": float(latest_row["volatility"]),
                "base_score": base_score,
                "sentiment_modifier": sentiment_mod,
                "composite_score": composite_score,
                "signal": signal,
                "thai_commentary": llm_result.get("thai_commentary", "")
            }
            
            pipeline_results.append(record)
            
            # Check for transition
            prev_plan_state = prev_signals.get(plan_id)
            if prev_plan_state:
                prev_signal = prev_plan_state.get("signal")
                if prev_signal and prev_signal != signal:
                    logger.info(f"Signal Transition detected for {plan_id}: {prev_signal} -> {signal}")
                    transitions.append({
                        "plan_id": plan_id,
                        "plan_name": plan_name,
                        "old_signal": prev_signal,
                        "new_signal": signal,
                        "composite_score": composite_score,
                        "thai_commentary": record["thai_commentary"]
                    })
            elif not self.sheets.is_connected():
                # For local/offline testing if no previous sheet states exist, log transitions mock
                logger.info(f"Calculated offline signal for {plan_id}: {signal} (score: {composite_score})")

        # 6. Save performance record back to Google Sheets
        if persist and self.sheets.is_connected() and pipeline_results:
            self._sync_synthetic_performance_sheet(pipeline_results)
            
        self.latest_results = pipeline_results
        logger.info("Pipeline update run complete.")
        return transitions

    def _sync_proxy_prices_sheet(self, prices_df: pd.DataFrame):
        """Helper to append only new proxy prices to prevent duplicate entries."""
        try:
            # Get latest price date in sheets
            existing_prices = self.sheets.get_proxy_prices()
            latest_date = None
            if existing_prices:
                latest_date = max(r["date"] for r in existing_prices)
                
            rows_to_save = []
            for date, row in prices_df.iterrows():
                date_str = date.strftime("%Y-%m-%d")
                if latest_date and date_str <= latest_date:
                    continue # Skip duplicates
                
                for ticker, price in row.items():
                    rows_to_save.append({
                        "date": date_str,
                        "ticker": ticker,
                        "price": float(price)
                    })
            
            if rows_to_save:
                self.sheets.save_proxy_prices(rows_to_save)
        except Exception as e:
            logger.error(f"Error syncing proxy prices to sheets: {e}")

    def _sync_synthetic_performance_sheet(self, pipeline_results: List[Dict[str, Any]]):
        """Helper to append performance records only if the date doesn't exist."""
        try:
            rows_to_save = []
            for res in pipeline_results:
                plan_id = res["plan_id"]
                date_str = res["date"]
                
                # Check if this date already has records for this plan
                existing = self.sheets.get_synthetic_performance(plan_id)
                if any(r["date"] == date_str for r in existing):
                    logger.info(f"Record for plan {plan_id} on {date_str} already exists in sheet. Skipping append.")
                    continue
                
                rows_to_save.append(res)
                
            if rows_to_save:
                self.sheets.save_synthetic_performance(rows_to_save)
        except Exception as e:
            logger.error(f"Error syncing synthetic performance to sheets: {e}")
