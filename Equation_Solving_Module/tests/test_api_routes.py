import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from src.api.routes import app

client = TestClient(app)

def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "Welcome" in response.json()["message"]

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

@patch("src.api.routes.level_2_solver")
def test_run_success(mock_solver):
    mock_solver.return_value = (
        "Step 1: 2*x = 10\nStep 2: x = 5\n\nFinal Result: x = 5",
        {"operation": "solve"}
    )
    
    response = client.post("/run", json={"query": "solve 2x=10"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["operation"] == "solve"
    assert data["final_result"] == "x = 5"
    assert "Step 1: 2*x = 10" in "\n".join(data["steps"])

@patch("src.api.routes.level_2_solver")
def test_run_exception(mock_solver):
    mock_solver.side_effect = Exception("Internal Error")
    
    response = client.post("/run", json={"query": "fail"})
    assert response.status_code == 500
    assert "Internal Error" in response.json()["detail"]
