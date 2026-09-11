import yfinance as yf
import pandas as pd
import numpy as np
import logging
from typing import Dict, Optional, Tuple, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class FXService:
    """
    Manages USD/THB exchange rates and computes transparent, rule-based FX-adjusted returns 
    considering GPF (กบข.) foreign currency hedging policies.
    """
    # GPF Baseline Hedging Guidelines:
    # - Foreign Debt: 100% hedged (currency risk minimized).
    # - Foreign Equity: Dynamic 50% - 80% hedged based on mathematical trend and volatility rules.
    # - Gold: 0% unhedged (natural currency buffer).
    BASELINE_HEDGE_RATIOS = {
        "global_debt": 1.0,
        "global_equity": 0.5,
        "gold": 0.0
    }

    def __init__(self, fallback_rate: float = 34.50):
        self.fallback_rate = fallback_rate

    def fetch_usd_thb_history(
        self, 
        start_date: str = "2020-01-01", 
        end_date: Optional[str] = None
    ) -> pd.Series:
        """Fetches daily USD/THB exchange rate series (THB=X)."""
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")

        try:
            df = yf.download("THB=X", start=start_date, end=end_date, progress=False)
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex):
                    s = df["Close"].iloc[:, 0] if "Close" in df else df.iloc[:, 0]
                elif "Close" in df.columns:
                    s = df["Close"]
                else:
                    s = df.iloc[:, 0]

                s = s.ffill().bfill()
                s.name = "USD_THB"
                return s
        except Exception as e:
            logger.warning(f"Failed to fetch live USD/THB from Yahoo Finance: {e}")

        # Synthetic fallback series
        dates = pd.date_range(start=start_date, end=end_date)
        return pd.Series(self.fallback_rate, index=dates, name="USD_THB")

    def get_latest_rate(self) -> float:
        """Fetches the most recent USD/THB spot exchange rate."""
        try:
            ticker = yf.Ticker("THB=X")
            fast_info = getattr(ticker, "fast_info", None)
            if fast_info and "last_price" in fast_info:
                return float(fast_info["last_price"])
            
            hist = ticker.history(period="5d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception as e:
            logger.warning(f"Failed to get spot USD/THB: {e}")

        return self.fallback_rate

    def calculate_dynamic_equity_hedge(self, fx_series: Optional[pd.Series] = None) -> Dict[str, Any]:
        """
        Calculates transparent, mathematical dynamic hedge ratio for Global Equities:
        1. Base Hedge: 50% (0.50)
        2. Trend Rule (THB Momentum):
           - If Spot < MA60 (THB strengthening / USD weakening):
             Hedge ratio adjusts to 75% (+0.25) to prevent currency drag on foreign equity returns.
           - If Spot >= MA60 (THB weakening / USD strengthening):
             Hedge ratio stays at 50% to capture currency tailwinds without paying excess forward premia.
        3. Volatility Z-Score Rule:
           - If rolling 30-day realized volatility exceeds 1.5 standard deviations of 1-year history:
             Hedge ratio increases by +5% (capped at 80% maximum) for systemic risk mitigation.
        """
        if fx_series is None or len(fx_series) < 60:
            # Fallback with spot check
            spot = self.get_latest_rate()
            return {
                "hedge_ratio": 0.50,
                "spot_rate": spot,
                "ma60": spot,
                "regime": "NEUTRAL_BASE",
                "volatility_30d": 0.05,
                "rationale": "สภาวะสมดุลพื้นฐาน: ป้องกันความเสี่ยงอัตราแลกเปลี่ยน 50%"
            }

        spot = float(fx_series.iloc[-1])
        ma60 = float(fx_series.rolling(window=60).mean().iloc[-1])

        # 30-day rolling daily volatility annualized
        pct_change = fx_series.pct_change().dropna()
        vol_30d = float(pct_change.iloc[-30:].std() * np.sqrt(252)) if len(pct_change) >= 30 else 0.05
        vol_1y = float(pct_change.iloc[-252:].std() * np.sqrt(252)) if len(pct_change) >= 252 else vol_30d
        vol_std = float(pct_change.iloc[-252:].std()) if len(pct_change) >= 252 else 0.01

        z_score = (vol_30d - vol_1y) / (vol_std * np.sqrt(252) + 1e-6)

        # Baseline
        hedge_ratio = 0.50
        regime = "NORMAL_UNHEDGED_ADVANTAGE"
        rationale = "เงินบาททรงตัวหรืออ่อนค่า (USD/THB ≥ MA60): คง Hedge 50% เพื่อรับกำไรจากค่าเงินดอลลาร์"

        # Trend Trigger: THB Appreciation
        if spot < ma60:
            hedge_ratio = 0.75
            regime = "THB_APPRECIATING_LOCK"
            rationale = "เงินบาทแข็งค่าต่อเนื่อง (USD/THB < MA60): ขยับ Hedge สู่ 75% เพื่อป้องกันผลตอบแทนต่างประเทศหดตัว"

        # High Volatility Trigger
        if z_score > 1.5:
            hedge_ratio = min(0.80, hedge_ratio + 0.05)
            regime += "_HIGH_VOL"
            rationale += " + ความผันผวนค่าเงินพุ่งสูง (>1.5σ): เพิ่มการป้องกันความเสี่ยงสูงสุด 80%"

        return {
            "hedge_ratio": round(hedge_ratio, 2),
            "spot_rate": round(spot, 2),
            "ma60": round(ma60, 2),
            "volatility_30d": round(vol_30d * 100, 2),
            "z_score": round(z_score, 2),
            "regime": regime,
            "rationale": rationale
        }

    def adjust_returns_for_fx(
        self,
        usd_returns: pd.Series,
        fx_series: pd.Series,
        hedge_ratio: float = 0.5
    ) -> pd.Series:
        """
        Adjusts USD-denominated asset returns to THB terms based on hedge ratio h:
        R_THB = R_USD + (1 - h) * R_FX + (1 - h) * R_USD * R_FX
        Where R_FX = (S_t / S_{t-1}) - 1
        """
        aligned_fx = fx_series.reindex(usd_returns.index).ffill().bfill()
        fx_returns = aligned_fx.pct_change().fillna(0.0)

        unhedged_portion = 1.0 - hedge_ratio
        thb_returns = usd_returns + (unhedged_portion * fx_returns) + (unhedged_portion * usd_returns * fx_returns)
        return thb_returns

    def adjust_price_series_for_fx(
        self,
        usd_prices: pd.Series,
        fx_series: pd.Series,
        hedge_ratio: float = 0.5
    ) -> pd.Series:
        """
        Converts a USD asset price series into synthetic THB NAV series 
        incorporating the hedge ratio.
        """
        usd_returns = usd_prices.pct_change().fillna(0.0)
        thb_returns = self.adjust_returns_for_fx(usd_returns, fx_series, hedge_ratio)

        # Compound from the first base price
        thb_prices = (1.0 + thb_returns).cumprod() * usd_prices.iloc[0]
        return thb_prices

    # Alias for compatibility
    compute_fx_adjusted_price_series = adjust_price_series_for_fx
