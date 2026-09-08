import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert "service" in response.json()

def test_get_signals():
    response = client.get("/api/signals")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    # Check that plans are returned
    if "main" in data:
        assert "signal" in data["main"]
        assert "composite_score" in data["main"]

def test_get_history():
    response = client.get("/api/history?plan_id=main")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    if len(data) > 0:
        assert "synthetic_nav" in data[0]
        assert "date" in data[0]

def test_trigger_sync():
    response = client.post("/api/trigger-sync")
    assert response.status_code == 200
    assert response.json()["status"] == "triggered"
