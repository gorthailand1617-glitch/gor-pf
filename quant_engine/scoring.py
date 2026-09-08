import pandas as pd
import numpy as np
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def calculate_base_score(df: pd.DataFrame) -> float:
    """
    Calculates the rule-based Base Score (0-70 scale) for the latest row of df.
    """
    if df.empty:
        return 35.0 # Neutral mid point fallback

    latest = df.iloc[-1]
    
    # 1. Trend (MA Crossover): 30 points if MA20 > MA60, 0 otherwise
    ma_score = 30.0 if latest["ma20"] > latest["ma60"] else 0.0
    
    # 2. Momentum (RSI): Max 15 points
    # High scores in bullish momentum (50-65), lower scores for overbought/bearish extremes
    rsi = latest["rsi"]
    if 50.0 <= rsi <= 65.0:
        rsi_score = 15.0
    elif 45.0 <= rsi < 50.0 or 65.0 < rsi <= 75.0:
        rsi_score = 10.0
    elif 35.0 <= rsi < 45.0 or 75.0 < rsi <= 80.0:
        rsi_score = 5.0
    else:
        rsi_score = 0.0 # Extreme oversold/bearish or extremely overbought
        
    # 3. Trend Strength (MACD): 15 points if MACD > Signal Line, 0 otherwise
    macd_score = 15.0 if latest["macd"] > latest["macd_signal"] else 0.0
    
    # 4. Volatility Regime: 10 points
    # 10 points if current volatility <= historical median volatility, 0 otherwise
    if len(df) > 1:
        median_vol = df["volatility"].median()
        vol_score = 10.0 if latest["volatility"] <= median_vol else 0.0
    else:
        vol_score = 5.0 # Neutral fallback
        
    base_score = ma_score + rsi_score + macd_score + vol_score
    
    logger.info(
        f"Base Score calculated: {base_score:.2f}/70.0 (MA: {ma_score}, RSI: {rsi_score}, MACD: {macd_score}, Vol: {vol_score})"
    )
    
    return float(base_score)
