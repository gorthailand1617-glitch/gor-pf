import yfinance as yf
import pandas as pd
import numpy as np
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

from data_pipeline.fx_service import FXService

# Default mapping for proxies
PROXY_TICKERS = {
    "TDEX.BK": "Thai Equity",
    "SPY": "Global Equity",
    "EEM": "Emerging Markets",
    "WHART.BK": "Thai Property/REITs",
    "BND": "Global Debt",
    "GLD": "Gold"
}

class MarketDataService:
    def __init__(self, fx_service: Optional[FXService] = None):
        self.fx_service = fx_service or FXService()

    def fetch_historical_prices(
        self, 
        tickers: List[str], 
        start_date: str, 
        end_date: Optional[str] = None,
        adjust_fx: bool = True
    ) -> pd.DataFrame:
        """
        Fetches daily adjusted close prices for tickers.
        Calculates synthetic fixed yield for FIXED_INCOME_YIELD ticker.
        """
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        # Filter out FIXED_INCOME_YIELD to fetch from yfinance
        yf_tickers = [t for t in tickers if t != "FIXED_INCOME_YIELD"]
        
        logger.info(f"Fetching yfinance data for: {yf_tickers} from {start_date} to {end_date}")
        
        data = pd.DataFrame()
        if yf_tickers:
            try:
                # Use yf.download to grab close prices
                df = yf.download(yf_tickers, start=start_date, end=end_date, progress=False)
                if isinstance(df.columns, pd.MultiIndex):
                    # If multiple tickers, df['Adj Close'] or df['Close'] will be a dataframe
                    if 'Adj Close' in df.columns:
                        data = df['Adj Close']
                    else:
                        data = df['Close']
                else:
                    # Single ticker returns a Series or a simple DataFrame
                    if 'Adj Close' in df.columns:
                        data = df[['Adj Close']]
                    elif 'Close' in df.columns:
                        data = df[['Close']]
                    else:
                        data = df
                    data.columns = yf_tickers
            except Exception as e:
                logger.error(f"Error downloading yfinance data: {e}", exc_info=True)
        
        # Clean data: fill missing values using forward fill and backward fill
        if not data.empty:
            data = data.ffill().bfill()
            # If any ticker was missed, create an empty series for it
            for t in yf_tickers:
                if t not in data.columns:
                    data[t] = 100.0 # fallback baseline price
        else:
            # Create a date range as index if data is empty
            date_range = pd.date_range(start=start_date, end=end_date)
            data = pd.DataFrame(index=date_range)
            for t in yf_tickers:
                data[t] = 100.0

        # Handle FIXED_INCOME_YIELD
        # Base daily compound return for 2.25% p.a. assuming 252 trading days
        fixed_annual_rate = 0.0225
        daily_rate = (1 + fixed_annual_rate) ** (1 / 252) - 1
        
        # Construct synthetic price series starting at 100.0
        n_days = len(data)
        fixed_prices = [100.0]
        for i in range(1, n_days):
            fixed_prices.append(fixed_prices[-1] * (1 + daily_rate))
            
        data["FIXED_INCOME_YIELD"] = fixed_prices

        # Apply FX & Hedging Adjustments to USD assets (SPY, EEM, BND, GLD)
        if adjust_fx:
            usd_tickers = [t for t in ["SPY", "EEM", "BND", "GLD"] if t in data.columns]
            if usd_tickers:
                try:
                    fx_series = self.fx_service.fetch_usd_thb_history(start_date=start_date, end_date=end_date)
                    for ticker in usd_tickers:
                        hedge = 1.0 if ticker == "BND" else 0.5 if ticker in ["SPY", "EEM"] else 0.0
                        data[ticker] = self.fx_service.compute_fx_adjusted_price_series(
                            data[ticker], fx_series, hedge_ratio=hedge
                        )
                except Exception as e:
                    logger.warning(f"Error applying FX adjustments: {e}")
        
        # Ensure index is datetime and format it
        data.index = pd.to_datetime(data.index)
        
        return data

    def fetch_market_news(self) -> List[str]:
        """
        Fetches recent market news headlines using yfinance tickers (SPY, ^SET50).
        """
        news_headlines = []
        target_tickers = ["SPY", "^SET50"]
        
        for ticker_symbol in target_tickers:
            try:
                ticker = yf.Ticker(ticker_symbol)
                news = ticker.news
                if news:
                    for item in news[:5]: # grab top 5 news items per ticker
                        title = item.get("title")
                        publisher = item.get("publisher", "Unknown")
                        if title:
                            news_headlines.append(f"[{ticker_symbol}] {title} ({publisher})")
            except Exception as e:
                logger.warning(f"Failed to fetch news for {ticker_symbol}: {e}")
                
        # If no news retrieved, add standard baseline headline
        if not news_headlines:
            news_headlines.append("Global and Thai market indicators remain neutral with typical trading volumes.")
            
        return news_headlines
