import pytest
from datetime import datetime, timedelta
from quant_engine.rebalance_opportunity import OpportunityDetector
from data_pipeline.gspread_client import GPFSpreadsheetClient
from api.main import get_portfolio_quota, get_portfolio_opportunity

@pytest.fixture
def sample_weights():
    return {
        "fixed_income": 0.20,
        "money_market": 0.20,
        "thai_equity": 0.10,
        "thai_property": 0.10,
        "global_equity": 0.15,
        "global_debt": 0.10,
        "gold": 0.15
    }

def test_opportunity_detector_high_conviction(sample_weights):
    detector = OpportunityDetector(max_rebalances=12)
    # Global equity and Gold are surging (BUY_HOLD with high score)
    # Thai equity is weak (REDUCE)
    signals = {
        "fixed_income": {"signal": "WATCH", "composite_score": 48.0},
        "money_market": {"signal": "WATCH", "composite_score": 45.0},
        "thai_equity": {"signal": "REDUCE", "composite_score": 32.0},
        "thai_property": {"signal": "WATCH", "composite_score": 50.0},
        "global_equity": {"signal": "BUY_HOLD", "composite_score": 85.0},
        "global_debt": {"signal": "WATCH", "composite_score": 46.0},
        "gold": {"signal": "BUY_HOLD", "composite_score": 78.0}
    }

    opp = detector.evaluate_opportunity(
        current_weights=sample_weights,
        signals=signals,
        quota_used_this_year=2,
        last_rebalance_date=datetime.now() - timedelta(days=20)
    )

    assert opp["is_opportunity"] is True
    assert opp["opportunity_type"] in ["CAPITAL_PRESERVATION", "PROFIT_MOMENTUM"]
    assert opp["quota_status"]["remaining"] == 10
    assert opp["quota_status"]["used"] == 2

    # Check alert formatting
    msg = detector.format_alert_message(opp)
    assert "สิทธิ์การเปลี่ยนแผนปี" in msg
    assert "2/12" in msg
    assert "10" in msg


def test_opportunity_detector_quota_exhausted(sample_weights):
    detector = OpportunityDetector(max_rebalances=12)
    signals = {
        "fixed_income": {"signal": "BUY_HOLD", "composite_score": 80.0},
        "money_market": {"signal": "BUY_HOLD", "composite_score": 80.0},
        "thai_equity": {"signal": "BUY_HOLD", "composite_score": 80.0},
        "thai_property": {"signal": "BUY_HOLD", "composite_score": 80.0},
        "global_equity": {"signal": "BUY_HOLD", "composite_score": 80.0},
        "global_debt": {"signal": "BUY_HOLD", "composite_score": 80.0},
        "gold": {"signal": "BUY_HOLD", "composite_score": 80.0}
    }

    opp = detector.evaluate_opportunity(
        current_weights=sample_weights,
        signals=signals,
        quota_used_this_year=12,  # All 12 quotas exhausted!
        last_rebalance_date=datetime.now() - timedelta(days=20)
    )

    assert opp["is_opportunity"] is False
    assert opp["opportunity_type"] == "QUOTA_EXHAUSTED"
    assert opp["quota_status"]["remaining"] == 0


def test_opportunity_detector_cooldown(sample_weights):
    detector = OpportunityDetector(max_rebalances=12)
    # Moderate bullish signals, but rebalance was 2 days ago
    signals = {
        "fixed_income": {"signal": "WATCH", "composite_score": 52.0},
        "money_market": {"signal": "WATCH", "composite_score": 50.0},
        "thai_equity": {"signal": "WATCH", "composite_score": 55.0},
        "thai_property": {"signal": "WATCH", "composite_score": 52.0},
        "global_equity": {"signal": "BUY_HOLD", "composite_score": 72.0},
        "global_debt": {"signal": "WATCH", "composite_score": 50.0},
        "gold": {"signal": "BUY_HOLD", "composite_score": 71.0}
    }

    opp = detector.evaluate_opportunity(
        current_weights=sample_weights,
        signals=signals,
        quota_used_this_year=1,
        last_rebalance_date=datetime.now() - timedelta(days=2)  # Within 5-day cooldown!
    )

    assert opp["is_opportunity"] is False
    assert opp["opportunity_type"] == "COOLDOWN"


def test_sheets_quota_functions():
    sheets = GPFSpreadsheetClient()
    status = sheets.get_annual_quota_status("client_user")
    assert "year" in status
    assert status["max_allowed"] == 12
    assert "used" in status
    assert "remaining" in status
    assert status["used"] + status["remaining"] == 12


def test_api_quota_endpoint_direct():
    sheets = GPFSpreadsheetClient()
    from data_pipeline.storage_provider import StorageProvider
    storage = StorageProvider()
    data = get_portfolio_quota(sheets, storage)
    assert "year" in data
    assert data["max_allowed"] == 12
    assert "used" in data
    assert "remaining" in data
    assert data["used"] + data["remaining"] == 12
