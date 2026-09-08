import pytest
from data_pipeline.storage_provider import StorageProvider
from quant_engine.rebalance_opportunity import OpportunityDetector
from data_pipeline.fx_service import FXService

def test_extreme_ages_and_life_path(tmp_path):
    test_db = str(tmp_path / "extreme_test.db")
    storage = StorageProvider(db_path=test_db)

    # 1. Very young user (18 years old)
    prof_young = storage.save_user_profile({
        "user_id": "youth",
        "birth_year": 2008,
        "risk_profile": "AGGRESSIVE"
    })
    assert prof_young["equity_cap"] == 0.80

    # 2. Senior retired user (85 years old)
    prof_senior = storage.save_user_profile({
        "user_id": "retiree",
        "birth_year": 1941,
        "risk_profile": "CONSERVATIVE"
    })
    assert prof_senior["equity_cap"] == 0.15

def test_quota_exhaustion_behavior(tmp_path):
    test_db = str(tmp_path / "quota_exhaust_test.db")
    storage = StorageProvider(db_path=test_db)
    user_id = "frequent_trader"

    # Execute 12 rebalances to exhaust quota
    for i in range(1, 13):
        res = storage.record_rebalance_execution(
            user_id=user_id,
            old_weights={"fixed_income": 0.5, "thai_equity": 0.5},
            new_weights={"fixed_income": 0.6, "thai_equity": 0.4},
            score_before=50.0,
            score_after=55.0,
            reason=f"Trade {i}"
        )
        assert res["remaining"] == 12 - i

    # Check status
    quota = storage.get_annual_quota_status(user_id)
    assert quota["used"] == 12
    assert quota["remaining"] == 0

    # OpportunityDetector must reject new opportunities when quota is 0
    detector = OpportunityDetector(max_rebalances=12)
    opp = detector.evaluate_opportunity(
        current_weights={"fixed_income": 0.5, "thai_equity": 0.5},
        signals={"fixed_income": {"signal": "WATCH", "composite_score": 50.0}, "thai_equity": {"signal": "BUY_HOLD", "composite_score": 90.0}},
        quota_used_this_year=12
    )
    assert opp["is_opportunity"] is False
    assert "ครบ" in opp["reason"]

def test_fx_service_fallback_on_network_error(monkeypatch):
    fx = FXService(fallback_rate=34.50)
    
    def mock_download_fail(*args, **kwargs):
        raise ConnectionError("Yahoo Finance Offline")

    import yfinance as yf
    monkeypatch.setattr(yf, "download", mock_download_fail)

    # Should not crash, returns fallback series with 34.50
    series = fx.fetch_usd_thb_history("2024-01-01", "2024-01-10")
    assert not series.empty
    assert series.iloc[0] == 34.50
