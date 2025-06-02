import pytest
import json
from fastapi.testclient import TestClient
from main import app

def test_new_import_endpoint():
    """Тест нового POST endpoint с JSON body."""
    client = TestClient(app)
    
    # Тестовые данные
    test_products = [
        {
            "category": "electricity_plan",
            "source_url": "https://example.com/plan",
            "provider_name": "Test Provider",
            "product_id": "test-001",
            "name": "Test Plan",
            "available": True,
            "price_kwh": 0.15,
            "raw_data": {"test": True}
        }
    ]
    
    # Тест успешного импорта
    response = client.post("/products/import", json=test_products)
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test Plan"
    
    print("✅ Новый import endpoint работает!")

def test_legacy_import_endpoint():
    """Тест legacy endpoint для backward compatibility."""
    client = TestClient(app)
    
    raw_json = '''[{
        "category": "mobile_plan",
        "source_url": "https://example.com/mobile",
        "provider_name": "Mobile Provider",
        "product_id": "mobile-001",
        "name": "Mobile Plan",
        "available": true,
        "monthly_cost": 30.0,
        "raw_data": {"legacy": true}
    }]'''
    
    response = client.post(
        "/products/import_legacy", 
        data=raw_json,
        headers={"Content-Type": "text/plain"}
    )
    assert response.status_code == 200
    
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Mobile Plan"
    
    print("✅ Legacy import endpoint работает!")

def test_validation_errors():
    """Тест обработки ошибок валидации."""
    client = TestClient(app)
    
    # Невалидные данные
    invalid_data = [
        {
            "category": "invalid_category",  # Неверная категория
            "source_url": "not-a-url",      # Неверный URL
            "provider_name": "",             # Пустое имя
            "available": "not_boolean"       # Неверный тип
        }
    ]
    
    response = client.post("/products/import", json=invalid_data)
    assert response.status_code == 422
    
    error_detail = response.json()["detail"]
    print(f"✅ Валидация ошибок работает: {error_detail}")

def test_get_products_after_import():
    """Тест получения продуктов после импорта."""
    client = TestClient(app)
    
    # Сначала импортируем
    test_product = [{
        "category": "internet_plan",
        "source_url": "https://example.com/internet",
        "provider_name": "Internet Provider",
        "product_id": "int-001",
        "name": "Internet Plan",
        "available": True,
        "download_speed": 100.0,
        "raw_data": {}
    }]
    
    import_response = client.post("/products/import", json=test_product)
    assert import_response.status_code == 200
    
    # Теперь получаем все продукты
    get_response = client.get("/products")
    assert get_response.status_code == 200
    
    products = get_response.json()
    assert len(products) > 0
    
    # Проверяем, что наш продукт в списке
    internet_plans = [p for p in products if p["name"] == "Internet Plan"]
    assert len(internet_plans) == 1
    
    print("✅ GET /products после импорта работает!")

if __name__ == "__main__":
    test_new_import_endpoint()
    test_legacy_import_endpoint()
    test_validation_errors()
    test_get_products_after_import()
    print("🎉 Все тесты прошли успешно!")