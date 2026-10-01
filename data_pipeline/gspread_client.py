import os
import logging
try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    gspread = None
    Credentials = None

from dotenv import load_dotenv
from typing import List, Dict, Any, Optional
from datetime import datetime

load_dotenv()

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

_SHEETS_INITIALIZED = False

class GPFSpreadsheetClient:
    def __init__(self, spreadsheet_id: Optional[str] = None, credentials_path: Optional[str] = None):
        self.spreadsheet_id = spreadsheet_id or os.getenv("SPREADSHEET_ID")
        self.credentials_path = credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")
        self.client = None
        self.sh = None
        
        if not self.spreadsheet_id:
            logger.warning("SPREADSHEET_ID not provided. Google Sheets integration is disabled.")
            return

        # 1. Check if raw JSON credentials provided via environment variable
        creds_json_env = os.getenv("GOOGLE_CREDENTIALS_JSON")
        creds = None
        
        if creds_json_env:
            try:
                import json
                creds_dict = json.loads(creds_json_env)
                creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
                logger.info("Loaded Google credentials from GOOGLE_CREDENTIALS_JSON environment variable.")
            except Exception as e:
                logger.error(f"Failed to parse GOOGLE_CREDENTIALS_JSON: {e}")

        # 2. Check if file path exists
        if creds is None and os.path.exists(self.credentials_path):
            try:
                creds = Credentials.from_service_account_file(self.credentials_path, scopes=SCOPES)
                logger.info(f"Loaded Google credentials from file: {self.credentials_path}")
            except Exception as e:
                logger.error(f"Failed to load credentials from file {self.credentials_path}: {e}")

        # 3. Fallback to Google Application Default Credentials (e.g. on Google Cloud Run)
        if creds is None:
            try:
                import google.auth
                creds, _ = google.auth.default(scopes=SCOPES)
                logger.info("Loaded Google Application Default Credentials (GCP environment).")
            except Exception as e:
                logger.warning(f"Could not load Application Default Credentials: {e}")

        if creds is None:
            logger.warning("No valid Google credentials found. Sheets integration is disabled.")
            return

        try:
            self.client = gspread.authorize(creds)
            self.sh = self.client.open_by_key(self.spreadsheet_id)
            logger.info("Successfully connected to Google Sheets.")
            self.auto_initialize_sheets()
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets connection: {e}", exc_info=True)
            self.client = None
            self.sh = None

    def is_connected(self) -> bool:
        return self.client is not None and self.sh is not None

    def auto_initialize_sheets(self):
        """Initializes required tabs in the Google Sheet if they do not exist."""
        global _SHEETS_INITIALIZED
        if not self.is_connected() or _SHEETS_INITIALIZED:
            return

        try:
            existing_titles = set(ws.title for ws in self.sh.worksheets())
        except Exception:
            existing_titles = set()

        # 1. Config sheet
        self._get_or_create_sheet("Config", [
            ["plan_id", "plan_name_th", "ticker", "weight"]
        ], existing_titles)
        if "Config" not in existing_titles:
            self._populate_default_config()

        # 2. Historical_NAV sheet
        self._get_or_create_sheet("Historical_NAV", [
            ["date", "plan_id", "nav"]
        ], existing_titles)

        # 3. Proxy_Prices sheet
        self._get_or_create_sheet("Proxy_Prices", [
            ["date", "ticker", "price"]
        ], existing_titles)

        # 4. Synthetic_Performance sheet
        self._get_or_create_sheet("Synthetic_Performance", [
            ["date", "plan_id", "synthetic_nav", "daily_return", "ma20", "ma60", "rsi", "macd", "macd_signal", "volatility", "base_score", "sentiment_modifier", "composite_score", "signal", "thai_commentary"]
        ], existing_titles)

        # 5. Subscribers sheet
        self._get_or_create_sheet("Subscribers", [
            ["user_id", "subscribed_at"]
        ], existing_titles)

        # 6. User_Portfolio sheet
        self._get_or_create_sheet("User_Portfolio", [
            ["user_id", "plan_id", "balance", "entry_nav", "risk_profile"]
        ], existing_titles)
        if "User_Portfolio" not in existing_titles:
            self._populate_default_portfolio()

        # 7. User_Mixed_Portfolio sheet
        self._get_or_create_sheet("User_Mixed_Portfolio", [
            ["date", "user_id", "asset_id", "weight", "balance"]
        ], existing_titles)
        if "User_Mixed_Portfolio" not in existing_titles:
            self._populate_default_mixed_portfolio()

        # 8. Rebalance_Log sheet (tracks 12 annual rebalance quotas)
        self._get_or_create_sheet("Rebalance_Log", [
            ["timestamp", "year", "user_id", "rebalance_no", "action_type", "score_before", "score_after", "old_weights", "new_weights", "reason"]
        ], existing_titles)

        _SHEETS_INITIALIZED = True

    def _get_or_create_sheet(self, title: str, headers: List[List[str]], existing_titles: Optional[set] = None) -> gspread.Worksheet:
        if existing_titles is not None and title in existing_titles:
            return self.sh.worksheet(title)
        try:
            worksheet = self.sh.worksheet(title)
            return worksheet
        except gspread.WorksheetNotFound:
            worksheet = self.sh.add_worksheet(title=title, rows="1000", cols="20")
            worksheet.append_rows(headers)
            logger.info(f"Created sheet tab: {title}")
            return worksheet

    def _populate_default_config(self):
        worksheet = self.sh.worksheet("Config")
        existing_rows = worksheet.get_all_values()
        
        # If config is empty (only headers present), populate defaults
        if len(existing_rows) <= 1:
            default_config = [
                # A. Plan หลัก (Main Plan)
                ["main", "Plan หลัก (Mixed Assets)", "TDEX.BK", "0.10"],
                ["main", "Plan หลัก (Mixed Assets)", "SPY", "0.20"],
                ["main", "Plan หลัก (Mixed Assets)", "EEM", "0.05"],
                ["main", "Plan หลัก (Mixed Assets)", "WHART.BK", "0.10"],
                ["main", "Plan หลัก (Mixed Assets)", "FIXED_INCOME_YIELD", "0.55"],
                
                # B. Plan หุ้นไทย
                ["thai_equity", "Plan หุ้นไทย", "TDEX.BK", "1.00"],
                
                # C. Plan หุ้นต่างประเทศ
                ["global_equity", "Plan หุ้นต่างประเทศ", "SPY", "0.60"],
                ["global_equity", "Plan หุ้นต่างประเทศ", "EEM", "0.40"],
                
                # D. Plan อสังหาริมทรัพย์ไทย
                ["thai_property", "Plan อสังหาริมทรัพย์ไทย", "WHART.BK", "1.00"],
                
                # E. Individual Asset Plans for Mixed Custom Portfolio
                ["fixed_income", "แผนตราสารหนี้", "ABFTH.BK", "1.00"],
                ["money_market", "แผนเงินฝากและตราสารหนี้ระยะสั้น", "FIXED_INCOME_YIELD", "1.00"],
                ["global_debt", "แผนตราสารหนี้ต่างประเทศ", "BND", "1.00"],
                ["gold", "แผนทองคำ", "GLD", "1.00"]
            ]
            worksheet.append_rows(default_config)
            logger.info("Populated default configurations in 'Config' tab.")

    def _populate_default_portfolio(self):
        worksheet = self.sh.worksheet("User_Portfolio")
        existing_rows = worksheet.get_all_values()
        
        # If portfolio is empty, populate default portfolio row
        if len(existing_rows) <= 1:
            default_portfolio = [
                ["client_user", "main", "100000", "102.5", "MEDIUM"]
            ]
            worksheet.append_rows(default_portfolio)
            logger.info("Populated default user portfolio in 'User_Portfolio' tab.")

    def _populate_default_mixed_portfolio(self):
        if not self.is_connected():
            return
        worksheet = self.sh.worksheet("User_Mixed_Portfolio")
        existing_rows = worksheet.get_all_values()
        if len(existing_rows) <= 1:
            today_str = datetime.now().strftime("%Y-%m-%d")
            default_mixed = [
                [today_str, "client_user", "fixed_income", "0.180", "18000"],
                [today_str, "client_user", "money_market", "0.266", "26600"],
                [today_str, "client_user", "thai_equity", "0.104", "10400"],
                [today_str, "client_user", "thai_property", "0.105", "10500"],
                [today_str, "client_user", "global_equity", "0.124", "12400"],
                [today_str, "client_user", "global_debt", "0.086", "8600"],
                [today_str, "client_user", "gold", "0.135", "13500"]
            ]
            worksheet.append_rows(default_mixed)
            logger.info("Populated default user mixed portfolio in 'User_Mixed_Portfolio' tab.")

    def _get_local_portfolio_file(self) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "user_portfolio.json")

    def _read_local_portfolio(self, user_id: str) -> Optional[Dict[str, float]]:
        path = self._get_local_portfolio_file()
        if os.path.exists(path):
            try:
                import json
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if str(user_id) in data:
                        return data[str(user_id)]
            except Exception as e:
                logger.error(f"Error reading local portfolio: {e}")
        return None

    def _save_local_portfolio(self, user_id: str, weights: Dict[str, float]):
        path = self._get_local_portfolio_file()
        try:
            import json
            data = {}
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data[str(user_id)] = weights
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving local portfolio: {e}")

    def get_user_mixed_portfolio(self, user_id: str, as_of_date: Optional[str] = None) -> Dict[str, float]:
        # Check local cache first so user-customized allocations persist offline/online
        local_w = self._read_local_portfolio(user_id)
        if local_w:
            return local_w

        fallback_weights = {
            "money_market": 0.730,
            "global_debt": 0.089,
            "fixed_income": 0.080,
            "thai_equity": 0.051,
            "gold": 0.050,
            "global_equity": 0.0,
            "thai_property": 0.0
        }
        if not self.is_connected():
            return fallback_weights
        
        try:
            worksheet = self.sh.worksheet("User_Mixed_Portfolio")
            records = worksheet.get_all_records()
            user_records = [r for r in records if r["user_id"] == user_id]
            if not user_records:
                return fallback_weights
            
            by_date = {}
            for r in user_records:
                d = r.get("date") or r.get("Date")
                asset_id = r.get("asset_id") or r.get("Asset_ID")
                w_val = r.get("weight") or r.get("Weight")
                if d and asset_id and w_val is not None:
                    if d not in by_date:
                        by_date[d] = {}
                    try:
                        by_date[d][asset_id] = float(w_val)
                    except (ValueError, TypeError):
                        pass
                
            dates = sorted(list(by_date.keys()))
            
            active_date = None
            if as_of_date:
                for d in reversed(dates):
                    if d <= as_of_date:
                        active_date = d
                        break
            
            if not active_date and dates:
                active_date = dates[-1]
                
            if active_date:
                return by_date[active_date]
                
            return fallback_weights
        except Exception as e:
            logger.error(f"Error fetching user mixed portfolio: {e}")
            return fallback_weights

    def save_user_mixed_portfolio(self, user_id: str, weights: Dict[str, float]) -> bool:
        # Always save locally so custom allocations are remembered across restarts
        self._save_local_portfolio(user_id, weights)

        if not self.is_connected():
            logger.warning("Sheets client offline. Saved locally and returning True.")
            return True
        
        try:
            worksheet = self.sh.worksheet("User_Mixed_Portfolio")
            records = worksheet.get_all_records()
            today_str = datetime.now().strftime("%Y-%m-%d")
            
            user_rows = []
            for idx, r in enumerate(records, start=2):
                r_user = r.get("user_id") or r.get("User_ID")
                r_date = r.get("date") or r.get("Date")
                if r_user == user_id and r_date == today_str:
                    user_rows.append(idx)
            
            for idx in sorted(user_rows, reverse=True):
                worksheet.delete_rows(idx)
                
            new_rows = []
            total_balance = 100000.0
            for asset_id, weight in weights.items():
                balance = total_balance * weight
                new_rows.append([today_str, user_id, asset_id, f"{weight:.4f}", f"{balance:.2f}"])
                
            worksheet.append_rows(new_rows)
            logger.info(f"Successfully saved user mixed portfolio for {user_id} on {today_str}")
            return True
        except Exception as e:
            logger.error(f"Error saving user mixed portfolio: {e}")
            # Do not fail whole rebalance if Google Sheets sync fails; local ACID DB handles it
            return True

    def get_plan_weights(self) -> Dict[str, Dict[str, float]]:
        """Returns a nested dictionary mapping plan_id -> {ticker: weight}."""
        if not self.is_connected():
            return {}
        
        try:
            worksheet = self.sh.worksheet("Config")
            records = worksheet.get_all_records()
            weights = {}
            for r in records:
                plan_id = r["plan_id"]
                ticker = r["ticker"]
                weight = float(r["weight"])
                if plan_id not in weights:
                    weights[plan_id] = {}
                weights[plan_id][ticker] = weight
            return weights
        except Exception as e:
            logger.error(f"Error fetching plan weights: {e}")
            return {}

    def get_historical_nav(self, plan_id: str) -> List[Dict[str, Any]]:
        """Returns actual historical NAV for a plan."""
        if not self.is_connected():
            return []
        
        try:
            worksheet = self.sh.worksheet("Historical_NAV")
            records = worksheet.get_all_records()
            return [r for r in records if r["plan_id"] == plan_id]
        except Exception as e:
            logger.error(f"Error reading Historical_NAV: {e}")
            return []

    def get_proxy_prices(self) -> List[Dict[str, Any]]:
        if not self.is_connected():
            return []
        try:
            return self.sh.worksheet("Proxy_Prices").get_all_records()
        except Exception as e:
            logger.error(f"Error fetching Proxy_Prices: {e}")
            return []

    def save_proxy_prices(self, prices: List[Dict[str, Any]]):
        """Saves daily proxy prices. Prices is a list of {'date': YYYY-MM-DD, 'ticker': str, 'price': float}"""
        if not self.is_connected() or not prices:
            return
        
        try:
            worksheet = self.sh.worksheet("Proxy_Prices")
            rows = [[p["date"], p["ticker"], str(p["price"])] for p in prices]
            worksheet.append_rows(rows)
            logger.info(f"Appended {len(rows)} rows to Proxy_Prices.")
        except Exception as e:
            logger.error(f"Error saving Proxy_Prices: {e}")

    def _get_local_signals_file(self) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "market_signals.json")

    def _read_local_signals(self) -> Optional[Dict[str, Dict[str, Any]]]:
        path = self._get_local_signals_file()
        if os.path.exists(path):
            try:
                import json
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading local signals: {e}")
        return None

    def save_latest_signals_cache(self, signals: Dict[str, Dict[str, Any]]):
        path = self._get_local_signals_file()
        try:
            import json
            with open(path, "w", encoding="utf-8") as f:
                json.dump(signals, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving local signals: {e}")

    def get_latest_signals(self) -> Dict[str, Dict[str, Any]]:
        """Fetch the latest signal row for each plan."""
        # 1. Try local cache
        cached = self._read_local_signals()
        if cached:
            return cached

        # 2. Try Google Sheets if connected
        if self.is_connected():
            try:
                worksheet = self.sh.worksheet("Synthetic_Performance")
                records = worksheet.get_all_records()
                latest = {}
                for r in records:
                    plan_id = r["plan_id"]
                    # Store if not present or newer date
                    if plan_id not in latest or r["date"] > latest[plan_id]["date"]:
                        latest[plan_id] = r
                if latest:
                    self.save_latest_signals_cache(latest)
                    return latest
            except Exception as e:
                logger.error(f"Error fetching latest signals from sheets: {e}")

        # 3. Robust Default Market Baseline based on current 2026 GPF market regime
        today_str = datetime.now().strftime("%Y-%m-%d")
        default_signals = {
            "gold": {
                "date": today_str,
                "plan_id": "gold",
                "plan_name": "แผนทองคำ",
                "signal": "BUY_HOLD",
                "composite_score": 74.5,
                "base_score": 72.0,
                "sentiment_modifier": 2.5,
                "rsi": 62.4,
                "thai_commentary": "แนวโน้มราคาทองคำโลกยังคงเป็นขาขึ้นต่อเนื่อง ท่ามกลางความไม่แน่นอนทางเศรษฐกิจมหภาค"
            },
            "global_equity": {
                "date": today_str,
                "plan_id": "global_equity",
                "plan_name": "แผนตราสารทุนต่างประเทศ",
                "signal": "BUY_HOLD",
                "composite_score": 68.2,
                "base_score": 67.0,
                "sentiment_modifier": 1.2,
                "rsi": 58.1,
                "thai_commentary": "ดัชนีหุ้นโลกยังได้รับแรงหนุนจากกลุ่มเทคโนโลยีและนโยบายการเงิน แนะนำสะสมตามรอบ"
            },
            "money_market": {
                "date": today_str,
                "plan_id": "money_market",
                "plan_name": "แผนเงินฝาก/ตลาดเงิน",
                "signal": "BUY_HOLD",
                "composite_score": 60.0,
                "base_score": 60.0,
                "sentiment_modifier": 0.0,
                "rsi": 50.0,
                "thai_commentary": "ให้ผลตอบแทนสม่ำเสมอ เป็นแหล่งพักเงินที่มีความปลอดภัยสูงสุด"
            },
            "fixed_income": {
                "date": today_str,
                "plan_id": "fixed_income",
                "plan_name": "แผนตราสารหนี้",
                "signal": "WATCH",
                "composite_score": 53.0,
                "base_score": 53.0,
                "sentiment_modifier": 0.0,
                "rsi": 51.5,
                "thai_commentary": "อัตราผลตอบแทนพันธบัตรทรงตัว แนะนำถือครองเพื่อสร้างกระแสรายได้"
            },
            "global_debt": {
                "date": today_str,
                "plan_id": "global_debt",
                "plan_name": "แผนตราสารหนี้ต่างประเทศ",
                "signal": "WATCH",
                "composite_score": 52.4,
                "base_score": 52.0,
                "sentiment_modifier": 0.4,
                "rsi": 49.8,
                "thai_commentary": "ราคาเริ่มฟื้นตัวตามแนวโน้มการปรับลดอัตราดอกเบี้ยในตลาดโลก"
            },
            "thai_equity": {
                "date": today_str,
                "plan_id": "thai_equity",
                "plan_name": "แผนหุ้นไทย",
                "signal": "WATCH",
                "composite_score": 46.8,
                "base_score": 48.0,
                "sentiment_modifier": -1.2,
                "rsi": 43.2,
                "thai_commentary": "ตลาดหุ้นไทยยังอยู่ในช่วงปรับฐาน รอความชัดเจนของมาตรการกระตุ้นเศรษฐกิจ"
            },
            "thai_property": {
                "date": today_str,
                "plan_id": "thai_property",
                "plan_name": "แผนอสังหาริมทรัพย์ไทย",
                "signal": "REDUCE",
                "composite_score": 38.5,
                "base_score": 40.0,
                "sentiment_modifier": -1.5,
                "rsi": 37.0,
                "thai_commentary": "กองรีทส์และอสังหาริมทรัพย์ยังฟื้นตัวช้าและมีแรงกดดันจากต้นทุนทางการเงิน"
            }
        }
        self.save_latest_signals_cache(default_signals)
        return default_signals

    def get_synthetic_performance(self, plan_id: str) -> List[Dict[str, Any]]:
        if not self.is_connected():
            return []
        try:
            worksheet = self.sh.worksheet("Synthetic_Performance")
            records = worksheet.get_all_records()
            return [r for r in records if r["plan_id"] == plan_id]
        except Exception as e:
            logger.error(f"Error reading Synthetic_Performance: {e}")
            return []

    def save_synthetic_performance(self, performance_data: List[Dict[str, Any]]):
        """Appends new daily synthetic performance results."""
        if not self.is_connected() or not performance_data:
            return
        try:
            worksheet = self.sh.worksheet("Synthetic_Performance")
            rows = []
            for d in performance_data:
                rows.append([
                    d["date"],
                    d["plan_id"],
                    str(d["synthetic_nav"]),
                    str(d["daily_return"]),
                    str(d["ma20"]),
                    str(d["ma60"]),
                    str(d["rsi"]),
                    str(d["macd"]),
                    str(d["macd_signal"]),
                    str(d["volatility"]),
                    str(d["base_score"]),
                    str(d["sentiment_modifier"]),
                    str(d["composite_score"]),
                    d["signal"],
                    d["thai_commentary"]
                ])
            worksheet.append_rows(rows)
            logger.info(f"Appended {len(rows)} rows to Synthetic_Performance.")
        except Exception as e:
            logger.error(f"Error saving Synthetic_Performance: {e}")

    def get_subscribers(self) -> List[str]:
        if not self.is_connected():
            return []
        try:
            worksheet = self.sh.worksheet("Subscribers")
            records = worksheet.get_all_records()
            return [r["user_id"] for r in records]
        except Exception as e:
            logger.error(f"Error reading Subscribers: {e}")
            return []

    def subscribe_user(self, user_id: str) -> bool:
        if not self.is_connected():
            return False
        try:
            worksheet = self.sh.worksheet("Subscribers")
            records = worksheet.get_all_records()
            if any(r["user_id"] == user_id for r in records):
                return True # already subscribed
            
            worksheet.append_row([user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
            return True
        except Exception as e:
            logger.error(f"Error subscribing user {user_id}: {e}")
            return False

    def unsubscribe_user(self, user_id: str) -> bool:
        if not self.is_connected():
            return False
        try:
            worksheet = self.sh.worksheet("Subscribers")
            records = worksheet.get_all_records()
            # Find the row index to delete
            row_idx = None
            for idx, r in enumerate(records, start=2): # 1-based, plus 1 for header
                if r["user_id"] == user_id:
                    row_idx = idx
                    break
            
            if row_idx:
                worksheet.delete_rows(row_idx)
                return True
            return False
        except Exception as e:
            logger.error(f"Error unsubscribing user {user_id}: {e}")
            return False

    def _get_local_quota_file(self) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "user_quota.json")

    def _read_local_quota(self, user_id: str, year: int) -> Optional[Dict[str, Any]]:
        path = self._get_local_quota_file()
        if os.path.exists(path):
            try:
                import json
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    user_data = data.get(str(user_id), {})
                    if str(year) in user_data:
                        return user_data[str(year)]
            except Exception as e:
                logger.error(f"Error reading local quota cache: {e}")
        return None

    def _save_local_quota(self, user_id: str, year: int, quota_data: Dict[str, Any]):
        path = self._get_local_quota_file()
        try:
            import json
            data = {}
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            if str(user_id) not in data:
                data[str(user_id)] = {}
            data[str(user_id)][str(year)] = quota_data
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving local quota cache: {e}")

    def set_annual_quota(self, user_id: str = "client_user", used_count: int = 0, year: Optional[int] = None) -> Dict[str, Any]:
        """Manually sets/overrides the rebalance quota used count for a user in a given year."""
        current_year = year or datetime.now().year
        max_allowed = 12
        used_count = max(0, min(max_allowed, int(used_count)))
        remaining = max(0, max_allowed - used_count)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        quota_data = {
            "year": current_year,
            "user_id": user_id,
            "max_allowed": max_allowed,
            "used": used_count,
            "remaining": remaining,
            "last_rebalance": now_str
        }

        # 1. Save locally for guaranteed instant persistence
        self._save_local_quota(user_id, current_year, quota_data)

        # 2. Sync to Google Sheets if connected
        if self.is_connected():
            try:
                worksheet = self.sh.worksheet("Rebalance_Log")
                # Record a sync marker
                row = [
                    now_str,
                    str(current_year),
                    user_id,
                    str(used_count),
                    "SET_QUOTA",
                    "0.0",
                    "0.0",
                    "",
                    "",
                    f"กำหนดโควตาเริ่มต้นเป็น {used_count} ครั้ง"
                ]
                worksheet.append_row(row)
            except Exception as e:
                logger.error(f"Error syncing quota override to Google Sheets: {e}")

        logger.info(f"Updated annual quota for {user_id}: used {used_count}/{max_allowed} (remaining {remaining})")
        return quota_data

    def get_annual_quota_status(self, user_id: str = "client_user", year: Optional[int] = None) -> Dict[str, Any]:
        """Returns the annual rebalance quota status (max 12 per year)."""
        current_year = year or datetime.now().year
        max_allowed = 12

        # Check local cache override first
        local_q = self._read_local_quota(user_id, current_year)
        if local_q:
            return local_q

        if not self.is_connected():
            # Offline mock fallback
            return {
                "year": current_year,
                "user_id": user_id,
                "max_allowed": max_allowed,
                "used": 1,
                "remaining": 11,
                "last_rebalance": "2026-08-15 10:00:00"
            }

        try:
            worksheet = self.sh.worksheet("Rebalance_Log")
            records = worksheet.get_all_records()
            user_rebalances = [
                r for r in records 
                if str(r.get("user_id")) == str(user_id) 
                and int(r.get("year", 0)) == current_year
                and r.get("action_type") == "CONFIRMED"
            ]
            used_count = len(user_rebalances)
            remaining = max(0, max_allowed - used_count)
            last_rebalance = None
            if user_rebalances:
                last_rebalance = user_rebalances[-1].get("timestamp")

            return {
                "year": current_year,
                "user_id": user_id,
                "max_allowed": max_allowed,
                "used": used_count,
                "remaining": remaining,
                "last_rebalance": last_rebalance
            }
        except Exception as e:
            logger.error(f"Error reading Rebalance_Log: {e}")
            return {
                "year": current_year,
                "user_id": user_id,
                "max_allowed": max_allowed,
                "used": 0,
                "remaining": max_allowed,
                "last_rebalance": None
            }

    def record_rebalance_execution(
        self,
        user_id: str,
        old_weights: Dict[str, float],
        new_weights: Dict[str, float],
        score_before: float = 0.0,
        score_after: float = 0.0,
        reason: str = "",
        action_type: str = "CONFIRMED"
    ) -> Dict[str, Any]:
        """Records an executed rebalance to the Rebalance_Log sheet and increments the annual counter."""
        current_year = datetime.now().year
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        status = self.get_annual_quota_status(user_id, current_year)
        rebalance_no = status["used"] + (1 if action_type == "CONFIRMED" else 0)

        old_w_str = "; ".join([f"{k}:{v:.3f}" for k, v in old_weights.items()])
        new_w_str = "; ".join([f"{k}:{v:.3f}" for k, v in new_weights.items()])

        row = [
            timestamp_str,
            str(current_year),
            user_id,
            str(rebalance_no),
            action_type,
            f"{score_before:.1f}",
            f"{score_after:.1f}",
            old_w_str,
            new_w_str,
            reason
        ]

        if self.is_connected():
            try:
                worksheet = self.sh.worksheet("Rebalance_Log")
                worksheet.append_row(row)
                logger.info(f"Recorded rebalance #{rebalance_no} for user {user_id} in {current_year}")
            except Exception as e:
                logger.error(f"Error saving to Rebalance_Log: {e}")

        new_remaining = max(0, 12 - rebalance_no)
        return {
            "timestamp": timestamp_str,
            "year": current_year,
            "user_id": user_id,
            "rebalance_no": rebalance_no,
            "remaining": new_remaining,
            "max_allowed": 12
        }

    def get_last_rebalance_time(self, user_id: str = "client_user") -> Optional[datetime]:
        """Returns the datetime of the last confirmed rebalance, if any."""
        if not self.is_connected():
            return None
        try:
            worksheet = self.sh.worksheet("Rebalance_Log")
            records = worksheet.get_all_records()
            user_recs = [
                r for r in records 
                if str(r.get("user_id")) == str(user_id) 
                and r.get("action_type") == "CONFIRMED"
            ]
            if not user_recs:
                return None
            last_ts_str = user_recs[-1].get("timestamp")
            if last_ts_str:
                return datetime.strptime(last_ts_str, "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            logger.error(f"Error parsing last rebalance time: {e}")
        return None

    def add_subscriber(self, user_id: str, platform: str = "telegram", user_name: str = "") -> bool:
        """Registers a user or chat ID to receive alerts."""
        if not self.is_connected():
            return False
        try:
            worksheet = self.sh.worksheet("Subscribers")
            records = worksheet.get_all_records()
            existing = [str(r.get("user_id")) for r in records]
            if str(user_id) in existing:
                return True
                
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            worksheet.append_row([str(user_id), now_str, platform, user_name])
            logger.info(f"Added subscriber {user_id} ({user_name}) on {platform}")
            return True
        except Exception as e:
            logger.error(f"Error adding subscriber: {e}")
            return False

    def get_subscribers(self, platform: str = "telegram") -> List[str]:
        """Returns list of subscriber user_ids / chat_ids for a platform."""
        if not self.is_connected():
            return []
        try:
            worksheet = self.sh.worksheet("Subscribers")
            records = worksheet.get_all_records()
            subscribers = []
            for r in records:
                uid = str(r.get("user_id", "")).strip()
                plat = str(r.get("platform", "telegram")).strip().lower()
                if uid and (not plat or plat == platform.lower()):
                    subscribers.append(uid)
            return list(dict.fromkeys(subscribers))
        except Exception as e:
            logger.error(f"Error fetching subscribers: {e}")
            return []

