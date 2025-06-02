import pytest
import asyncio
from fastapi.testclient import TestClient
from main import app

def test_search_endpoint_validation_fix():
    """Тест исправления валидации параметров."""
    client = TestClient(app)
    
    # Тест 1: Корректные числовые параметры как строки
    response = client.get("/search?min_price=100.50&max_data_gb=50&min_contract_duration_months=12")
    assert response.status_code == 200
    
    # Тест 2: Пустые параметры
    response = client.get("/search?min_price=&max_data_gb=&min_contract_duration_months=")
    assert response.status_code == 200
    
    # Тест 3: Некорректные параметры
    response = client.get("/search?min_price=invalid_number")
    assert response.status_code == 422
    assert "Invalid number format" in response.json()["detail"]
    
    # Тест 4: Корректные смешанные параметры
    response = client.get("/search?product_type=mobile_plan&min_price=25.99&provider=TestProvider")
    assert response.status_code == 200
    
    print("✅ Все тесты валидации прошли успешно!")

if __name__ == "__main__":
    test_search_endpoint_validation_fix()