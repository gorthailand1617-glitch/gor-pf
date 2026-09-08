import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculates the 14-day Relative Strength Index (RSI)."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).copy()
    loss = (-delta.where(delta < 0, 0)).copy()

    # Use wilder's exponential moving average
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50) # Neutral default for missing data

def calculate_macd(
    series: pd.Series, 
    fast: int = 12, 
    slow: int = 26, 
    signal: int = 9
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates MACD, MACD Signal, and MACD Histogram."""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - signal_line
    return macd_line, signal_line, macd_hist

def calculate_indicators(prices_df: pd.DataFrame, weights: Dict[str, float]) -> pd.DataFrame:
    """
    Computes daily returns, builds Synthetic NAV, and calculates indicators.
    Returns a DataFrame with columns:
      - synthetic_nav
      - daily_return
      - ma20
      - ma60
      - rsi
      - macd
      - macd_signal
      - volatility
    """
    # 1. Compute daily returns for all tickers
    returns_df = prices_df.pct_change().fillna(0)

    # 2. Compute weighted daily return
    weighted_return = pd.Series(0.0, index=prices_df.index)
    for ticker, weight in weights.items():
        if ticker in returns_df.columns:
            weighted_return += returns_df[ticker] * weight

    # 3. Compounding Synthetic NAV (starting at 100.0)
    synthetic_nav = [100.0]
    for r in weighted_return.values[1:]:
        synthetic_nav.append(synthetic_nav[-1] * (1 + r))

    df = pd.DataFrame(index=prices_df.index)
    df["daily_return"] = weighted_return
    df["synthetic_nav"] = synthetic_nav

    # 4. Moving Averages
    df["ma20"] = df["synthetic_nav"].rolling(window=20, min_periods=1).mean()
    df["ma60"] = df["synthetic_nav"].rolling(window=60, min_periods=1).mean()

    # 5. RSI
    df["rsi"] = calculate_rsi(df["synthetic_nav"], period=14)

    # 6. MACD
    macd, macd_sig, _ = calculate_macd(df["synthetic_nav"])
    df["macd"] = macd
    df["macd_signal"] = macd_sig

    # 7. Volatility Regime (20-day rolling standard deviation of daily returns)
    df["volatility"] = df["daily_return"].rolling(window=20, min_periods=1).std() * np.sqrt(252) # Annualized
    df["volatility"] = df["volatility"].fillna(0.0)

    return df
