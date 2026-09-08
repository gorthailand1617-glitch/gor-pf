import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_get_portfolio_status():
    response = client.get("/api/portfolio/status")
    assert response.status_code == 200
    data = response.json()
    assert "weights" in data
    assert "history" in data
    assert isinstance(data["weights"], dict)
    assert isinstance(data["history"], list)
    # Check fallback weights
    assert "fixed_income" in data["weights"]
    assert data["weights"]["fixed_income"] == 0.18

def test_get_portfolio_optimization():
    response = client.get("/api/portfolio/optimize")
    assert response.status_code == 200
    data = response.json()
    assert "current_weights" in data
    assert "optimized_weights" in data
    assert "signals" in data
    assert "commentary" in data
    assert isinstance(data["optimized_weights"], dict)
    assert isinstance(data["signals"], dict)
    assert isinstance(data["commentary"], str)

def test_post_portfolio_rebalance():
    # Attempt to post a valid rebalance request
    payload = {
        "weights": {
            "fixed_income": 0.20,
            "money_market": 0.20,
            "thai_equity": 0.10,
            "thai_property": 0.10,
            "global_equity": 0.15,
            "global_debt": 0.10,
            "gold": 0.15
        }
    }
    response = client.post("/api/portfolio/rebalance", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"
