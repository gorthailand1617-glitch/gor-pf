import pytest
import pandas as pd
import numpy as np
from data_pipeline.fx_service import FXService

def test_dynamic_hedging_trend_rules():
    fx = FXService()
    
    # 1. Scenario A: THB Strengthening (USD/THB falls below MA60)
    # 60 days of 36.0, then drops to 34.0
    prices = [36.0] * 60 + [34.0] * 10
    dates = pd.date_range("2024-01-01", periods=len(prices))
    fx_series = pd.Series(prices, index=dates)

    hedge_res = fx.calculate_dynamic_equity_hedge(fx_series)
    assert hedge_res["spot_rate"] == 34.0
    assert hedge_res["spot_rate"] < hedge_res["ma60"]
    # Should adjust hedge to 75% or higher
    assert hedge_res["hedge_ratio"] >= 0.75
    assert "THB_APPRECIATING" in hedge_res["regime"]

    # 2. Scenario B: THB Weakening / Depreciating (USD/THB rises above MA60)
    # 60 days of 34.0, then rises to 36.5
    prices_b = [34.0] * 60 + [36.5] * 10
    fx_series_b = pd.Series(prices_b, index=dates)

    hedge_res_b = fx.calculate_dynamic_equity_hedge(fx_series_b)
    assert hedge_res_b["spot_rate"] == 36.5
    assert hedge_res_b["spot_rate"] > hedge_res_b["ma60"]
    # Should stay at baseline 50% to capture currency windfall
    assert hedge_res_b["hedge_ratio"] == 0.50

def test_dynamic_hedging_volatility_spike():
    fx = FXService()
    # High volatility series with rapid swings
    np.random.seed(123)
    base = 35.0
    returns = np.random.normal(0.0, 0.03, 70) # very high 3% daily volatility!
    prices = [base]
    for r in returns:
        prices.append(prices[-1] * (1.0 + r))
    
    dates = pd.date_range("2024-01-01", periods=len(prices))
    fx_series = pd.Series(prices, index=dates)

    hedge_res = fx.calculate_dynamic_equity_hedge(fx_series)
    # Should detect high volatility and cap hedge ratio up to 80%
    assert hedge_res["hedge_ratio"] <= 0.80
    assert hedge_res["volatility_30d"] > 0
