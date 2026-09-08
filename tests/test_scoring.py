import pytest
import pandas as pd
from quant_engine.scoring import calculate_base_score

def test_calculate_base_score_empty():
    df = pd.DataFrame()
    score = calculate_base_score(df)
    assert score == 35.0 # Fallback default

def test_calculate_base_score_bullish():
    # Build a fake dataframe with strongly bullish indicators
    df = pd.DataFrame([{
        "ma20": 105.0,
        "ma60": 100.0, # Bullish crossover
        "rsi": 55.0,   # Strong bullish momentum (+15)
        "macd": 0.5,
        "macd_signal": 0.2, # Bullish MACD (+15)
        "volatility": 0.05
    }])
    # Overwrite median logic by adding a second row
    df2 = pd.DataFrame([
        {"ma20": 105.0, "ma60": 100.0, "rsi": 55.0, "macd": 0.5, "macd_signal": 0.2, "volatility": 0.05},
        {"ma20": 106.0, "ma60": 100.0, "rsi": 56.0, "macd": 0.6, "macd_signal": 0.2, "volatility": 0.04}
    ])
    score = calculate_base_score(df2)
    # Crossover: 30
    # RSI: 15
    # MACD: 15
    # Volatility <= Median (0.04 <= 0.045): 10
    # Total score should be 70
    assert score == 70.0
