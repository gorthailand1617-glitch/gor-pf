import pytest
import os
import pandas as pd
from datetime import datetime
from data_pipeline.fx_service import FXService
from data_pipeline.storage_provider import StorageProvider
from quant_engine.rebalance_opportunity import OpportunityDetector
from quant_engine.backtest import GPFBacktestEngine

def test_fx_service_hedging_calculation():
    fx = FXService(fallback_rate=34.0)
    
    # Test unhedged return: Asset up 10%, USD/THB up 5% (THB depreciates) -> Return in THB should be ~15.5%
    usd_ret = pd.Series([0.0, 0.10])
    fx_series = pd.Series([34.0, 35.70]) # +5%
    
    # 0% Hedged
    adj_unhedged = fx.adjust_returns_for_fx(usd_ret, fx_series, hedge_ratio=0.0)
    assert round(adj_unhedged.iloc[-1], 3) == 0.150 or round(adj_unhedged.iloc[-1], 3) == 0.155

    # 100% Hedged: FX change neutralized -> Return remains 10%
    adj_hedged = fx.adjust_returns_for_fx(usd_ret, fx_series, hedge_ratio=1.0)
    assert round(adj_hedged.iloc[-1], 2) == 0.10


def test_storage_provider_life_path(tmp_path):
    test_db = str(tmp_path / "test_governance.db")
    storage = StorageProvider(db_path=test_db)

    # 1. User Age 58 (Born 1968 in 2026) -> Equity cap must be 0.20
    prof = storage.save_user_profile({
        "user_id": "test_senior",
        "birth_year": 1968,
        "risk_profile": "MODERATE"
    })
    assert prof["age"] == 58
    assert prof["equity_cap"] <= 0.25

    # 2. User Age 25 (Born 2001 in 2026) -> Equity cap can be up to 0.70-0.80
    young_prof = storage.save_user_profile({
        "user_id": "test_young",
        "birth_year": 2001,
        "risk_profile": "AGGRESSIVE"
    })
    assert young_prof["age"] == 25
    assert young_prof["equity_cap"] >= 0.70

    # 3. Test ACID rebalance logging
    log_res = storage.record_rebalance_execution(
        user_id="test_senior",
        old_weights={"fixed_income": 0.8, "thai_equity": 0.2},
        new_weights={"fixed_income": 0.9, "thai_equity": 0.1},
        score_before=50.0,
        score_after=65.0,
        reason="Test Senior Capital Preservation"
    )
    assert log_res["rebalance_no"] == 1
    assert log_res["remaining"] == 11

    quota = storage.get_annual_quota_status("test_senior")
    assert quota["used"] == 1
    assert quota["remaining"] == 11


def test_opportunity_detector_life_path_cap():
    detector = OpportunityDetector(max_rebalances=12)
    current_weights = {
        "fixed_income": 0.20,
        "money_market": 0.20,
        "thai_equity": 0.20,
        "global_equity": 0.40
    }
    # Both equities have extreme BUY_HOLD signals (score 90)
    signals = {
        "fixed_income": {"signal": "WATCH", "composite_score": 50.0},
        "money_market": {"signal": "WATCH", "composite_score": 50.0},
        "thai_equity": {"signal": "BUY_HOLD", "composite_score": 90.0},
        "global_equity": {"signal": "BUY_HOLD", "composite_score": 95.0}
    }

    # Senior User with 20% Life Path Equity Cap
    opt_weights = detector.calculate_optimized_weights(
        current_weights=current_weights,
        signals=signals,
        equity_cap=0.20
    )

    total_equity = opt_weights.get("thai_equity", 0.0) + opt_weights.get("global_equity", 0.0)
    # Total equity must strictly NOT exceed 0.20!
    assert total_equity <= 0.205
    assert opt_weights["fixed_income"] + opt_weights["money_market"] >= 0.795


def test_backtest_engine_simulation():
    engine = GPFBacktestEngine()
    profile = {"equity_cap": 0.50}
    results = engine.run_simulation(start_year=2020, end_year=2026, user_profile=profile)

    assert "metrics" in results
    assert "strategy" in results["metrics"]
    assert "main_plan" in results["metrics"]
    assert "global_equity" in results["metrics"]

    # Verify metrics exist
    assert results["metrics"]["strategy"]["cagr"] > 0
    assert results["metrics"]["strategy"]["mdd"] < 0
    assert results["metrics"]["strategy"]["sharpe"] > 0

    # Verify Quota compliance: All years must have rebalances <= 12
    assert results["quota_compliance"]["compliant"] is True
    for yr, count in results["quota_compliance"]["annual_usage"].items():
        assert count <= 12

    # Verify Crisis Scenarios are included
    assert len(results["crisis_scenarios"]) >= 2
    assert any("COVID-19" in cs["crisis_name"] for cs in results["crisis_scenarios"])
