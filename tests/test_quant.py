import pytest
import pandas as pd
import numpy as np
from quant_engine.metrics import calculate_rsi, calculate_macd, calculate_indicators

def test_calculate_rsi():
    # Create a simple trend series
    prices = pd.Series([100 + i for i in range(20)])
    rsi = calculate_rsi(prices, period=14)
    assert len(rsi) == 20
    assert rsi.iloc[-1] > 50.0 # Uptrend should be bullish RSI

def test_calculate_macd():
    prices = pd.Series([100 * (1.01 ** i) for i in range(40)])
    macd, signal, hist = calculate_macd(prices)
    assert len(macd) == 40
    assert len(signal) == 40
    assert len(hist) == 40

def test_calculate_indicators():
    # Create fake prices dataframe
    dates = pd.date_range(start="2026-01-01", periods=30)
    prices_df = pd.DataFrame({
        "TDEX.BK": np.linspace(10, 11, 30),
        "SPY": np.linspace(500, 520, 30)
    }, index=dates)
    
    weights = {"TDEX.BK": 0.5, "SPY": 0.5}
    indicators = calculate_indicators(prices_df, weights)
    
    assert "synthetic_nav" in indicators.columns
    assert "daily_return" in indicators.columns
    assert "ma20" in indicators.columns
    assert "ma60" in indicators.columns
    assert "rsi" in indicators.columns
    assert "macd" in indicators.columns
    assert "macd_signal" in indicators.columns
    assert "volatility" in indicators.columns
    
    # Synthetic NAV should start at 100.0
    assert indicators["synthetic_nav"].iloc[0] == 100.0
